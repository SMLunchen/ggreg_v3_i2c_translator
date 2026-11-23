/*
 * GGreg20_V3 -> I2C translator, register compatible with ClimateGuard RadSens
 * Target: ATtiny1614 (tinyAVR 1-series), bare metal, factory fuses.
 *
 * Pins
 *   PA4  LED (active high)
 *   PA5  GEIGER_EN (high = GGreg20 supply switched on)
 *   PA6  PULSE_IN  (GGreg20 OUT, active low; PA6 is a fully asynchronous pin,
 *                   so even very short pulses wake the MCU from power-down)
 *   PB0  SCL, PB1 SDA (TWI client, wakes from power-down on address match)
 *   PB2/PB3 optional 32.768 kHz crystal
 *   PA0  UPDI
 *
 * Power concept
 *   The MCU sits in power-down (~1 uA incl. 1 Hz PIT) and only wakes for
 *     - a Geiger pulse (pin interrupt, a few microseconds of work)
 *     - the 1 Hz tick (window bookkeeping, duty-cycle state machine)
 *     - an I2C address match
 *   Dose-rate values are computed lazily when the host actually talks to us.
 *
 * All measurement state is owned by interrupt handlers (which never nest on
 * AVR), the main loop only handles sleep, the LED flash and EEPROM writes.
 */
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <avr/wdt.h>
#include <util/delay.h>
#include <stdbool.h>
#include <stdint.h>

#include "config.h"

#if STATIC_WINDOW_S > 255 || DYNAMIC_WINDOW_MAX_S > STATIC_WINDOW_S
#error "window sizes: STATIC_WINDOW_S <= 255 and DYNAMIC_WINDOW_MAX_S <= STATIC_WINDOW_S"
#endif

/* ---- pins ------------------------------------------------------------- */
#define LED_bm          PIN4_bm         /* PA4 */
#define GEIGER_EN_bm    PIN5_bm         /* PA5 */
#define PULSE_bm        PIN6_bm         /* PA6 */
#define PULSE_PINCTRL   PORTA.PIN6CTRL

#if PULSE_PULLUP
#define PULSE_ACTIVE_CFG (PORT_ISC_FALLING_gc | PORT_PULLUPEN_bm)
#else
#define PULSE_ACTIVE_CFG (PORT_ISC_FALLING_gc)
#endif

/* ---- register map ----------------------------------------------------- */
#define REG_ID          0x00
#define REG_FW          0x01
#define REG_DYN         0x03    /* 3 bytes, MSB first, 0.1 uR/h */
#define REG_STATIC      0x06    /* 3 bytes, MSB first, 0.1 uR/h */
#define REG_PULSES      0x09    /* 2 bytes, MSB first, reset on read */
#define REG_LP_MODE     0x0C
#define REG_ADDR        0x10
#define REG_HV          0x11
#define REG_SENS        0x12    /* 2 bytes, LSB first (as in the RadSens library) */
#define REG_LED         0x14
/* extensions (not part of RadSens) */
#define REG_PERIOD      0x20    /* 2 bytes, LSB first, seconds */
#define REG_MEASURE     0x22    /* 2 bytes, LSB first, seconds */
#define REG_WARMUP      0x24    /* seconds */
#define REG_STATUS      0x25    /* bit0 GGreg powered, bit1 counting, bit2 static window full, bit3 duty cycling active */
#define REG_WINDOW_S    0x26    /* 2 bytes, LSB first: seconds currently in static window */
#define REG_PHASE_LEFT  0x28    /* 2 bytes, LSB first: seconds left in current phase */

/* ---- persistent configuration ----------------------------------------- */
typedef struct {
    uint8_t  magic;
    uint8_t  addr;
    uint16_t sens;
    uint8_t  led;
    uint8_t  lp_mode;
    uint16_t period;
    uint16_t measure;
    uint8_t  warmup;
    uint8_t  csum;
} config_t;

#define CFG_MAGIC 0xA7

static config_t cfg;
static volatile uint8_t cfg_dirty;      /* set by TWI ISR, saved by main loop */

static uint8_t cfg_csum(const config_t *c)
{
    const uint8_t *p = (const uint8_t *)c;
    uint8_t x = 0x5A;
    for (uint8_t i = 0; i < sizeof(config_t) - 1; i++)
        x ^= p[i];
    return x;
}

static void cfg_load(void)
{
    const uint8_t *ee = (const uint8_t *)MAPPED_EEPROM_START;
    uint8_t *p = (uint8_t *)&cfg;
    for (uint8_t i = 0; i < sizeof(config_t); i++)
        p[i] = ee[i];
    if (cfg.magic == CFG_MAGIC && cfg.csum == cfg_csum(&cfg) &&
        cfg.addr >= 0x03 && cfg.addr <= 0x77)
        return;
    cfg.magic   = CFG_MAGIC;
    cfg.addr    = I2C_ADDR_DEFAULT;
    cfg.sens    = SENSITIVITY_DEFAULT;
    cfg.led     = LED_DEFAULT;
    cfg.lp_mode = LP_MODE_DEFAULT;
    cfg.period  = CYCLE_PERIOD_DEFAULT;
    cfg.measure = MEASURE_TIME_DEFAULT;
    cfg.warmup  = WARMUP_DEFAULT;
}

/* Called from the main loop only. All config bytes live in one EEPROM page,
 * so one erase/write cycle covers every byte that changed. */
static void cfg_save(void)
{
    config_t snap;
    cli();
    snap = cfg;
    cfg_dirty = 0;
    sei();
    snap.csum = cfg_csum(&snap);

    volatile uint8_t *ee = (volatile uint8_t *)MAPPED_EEPROM_START;
    const uint8_t *p = (const uint8_t *)&snap;
    bool changed = false;

    while (NVMCTRL.STATUS & NVMCTRL_EEBUSY_bm) {}
    for (uint8_t i = 0; i < sizeof(config_t); i++) {
        if (ee[i] != p[i]) {
            ee[i] = p[i];               /* loads the page buffer */
            changed = true;
        }
    }
    if (changed) {
        _PROTECTED_WRITE_SPM(NVMCTRL.CTRLA, NVMCTRL_CMD_PAGEERASEWRITE_gc);
        while (NVMCTRL.STATUS & NVMCTRL_EEBUSY_bm) {}
    }
    /* a new I2C address becomes active once the bus is idle again */
    if (TWI0.SADDR != (uint8_t)(snap.addr << 1))
        TWI0.SADDR = snap.addr << 1;
}

/* ---- measurement state (ISR context only) ------------------------------ */
static uint16_t bins[STATIC_WINDOW_S];  /* pulses per measured second, ring buffer */
static uint8_t  head;                   /* next slot to write */
static uint8_t  filled;                 /* valid seconds in ring */
static uint32_t static_sum;             /* sum of all valid bins */
static uint16_t cur_bin;                /* pulses in the running second */
static uint16_t pulse_cnt;              /* reg 0x09, reset on read */
static uint8_t  pulse_latch_lo;
static bool     values_dirty;
static uint32_t val_dyn, val_static;    /* 0.1 uR/h */

enum { PH_OFF, PH_WARMUP, PH_MEASURE };
static uint8_t  phase;
static uint16_t phase_left;             /* seconds left in phase (0 = no limit) */
static uint8_t  hv_enable = 1;          /* reg 0x11 */

static volatile uint8_t tick_flag;
static volatile uint8_t led_on;
static volatile uint8_t twi_busy;
static uint8_t twi_busy_ticks;
static uint8_t reg_ptr;
static bool    twi_first;               /* next written byte is the register pointer */
static bool    twi_tx_started;

/* Dose rate in 0.1 uR/h:  36000 * n / (sens * t)   (RadSens datasheet 3.2) */
static uint32_t dose_rate(uint32_t n, uint8_t t)
{
    if (cfg.sens == 0 || t == 0)
        return 0;
    uint32_t d = (uint32_t)cfg.sens * t;        /* <= 65535 * 255 */
    if (n > 1193046UL)
        n = 1193046UL;                          /* keeps n * 3600 inside 32 bit */
    uint32_t x = n * 3600UL;
    uint32_t q = x / d;
    uint32_t r = x % d;
    if (q > 1677721UL)
        return 0xFFFFFFUL;
    uint32_t v = q * 10 + (r * 10 + d / 2) / d;
    return v > 0xFFFFFFUL ? 0xFFFFFFUL : v;
}

static void recompute(void)
{
    /* dynamic window: go back in time until enough pulses are collected */
    uint8_t lim = filled < DYNAMIC_WINDOW_MAX_S ? filled : DYNAMIC_WINDOW_MAX_S;
    uint8_t idx = head, n = 0;
    uint32_t acc = 0;
    while (n < lim) {
        idx = idx ? idx - 1 : STATIC_WINDOW_S - 1;
        acc += bins[idx];
        n++;
        if (acc >= DYNAMIC_TARGET_COUNTS)
            break;
    }
    val_dyn = dose_rate(acc, n);
    val_static = dose_rate(static_sum, filled);
    values_dirty = false;
}

static void push_bin(void)
{
    uint16_t c = cur_bin;
    cur_bin = 0;
    if (filled == STATIC_WINDOW_S)
        static_sum -= bins[head];
    else
        filled++;
    bins[head] = c;
    static_sum += c;
    if (++head == STATIC_WINDOW_S)
        head = 0;
    values_dirty = true;
}

/* ---- duty-cycle state machine (1 Hz, ISR context) ---------------------- */
static bool cycling(void)
{
    return cfg.lp_mode && cfg.measure != 0 &&
           (uint32_t)cfg.period > (uint32_t)cfg.measure + cfg.warmup;
}

static void enter_off(uint16_t seconds)
{
    PULSE_PINCTRL = PORT_ISC_INPUT_DISABLE_gc;
    PORTA.OUTCLR = GEIGER_EN_bm | LED_bm;
    phase = PH_OFF;
    phase_left = seconds;
}

static void enter_measure(void)
{
    cur_bin = 0;
    PORTA.INTFLAGS = PULSE_bm;
    PULSE_PINCTRL = PULSE_ACTIVE_CFG;
    phase = PH_MEASURE;
    phase_left = cycling() ? cfg.measure : 0;
}

static void enter_warmup(void)
{
    PORTA.OUTSET = GEIGER_EN_bm;
    phase = PH_WARMUP;
    phase_left = cfg.warmup;
    if (phase_left == 0)
        enter_measure();
}

static void phase_tick(void)
{
    if (!hv_enable) {                   /* host switched the "HV generator" off */
        if (phase != PH_OFF)
            enter_off(0);
        phase_left = 0;
        return;
    }
    switch (phase) {
    case PH_OFF:
        if (!cycling())
            phase_left = 0;
        if (phase_left)
            phase_left--;
        if (phase_left == 0)
            enter_warmup();
        break;
    case PH_WARMUP:
        if (phase_left)
            phase_left--;
        if (phase_left == 0)
            enter_measure();
        break;
    default: /* PH_MEASURE */
        push_bin();
        if (cycling()) {
            if (phase_left)
                phase_left--;
            if (phase_left == 0)
                enter_off(cfg.period - cfg.measure - cfg.warmup);
        } else {
            phase_left = 0;
        }
        break;
    }
}

/* ---- I2C register access (ISR context) --------------------------------- */
static uint8_t reg_read(uint8_t r)
{
    switch (r) {
    case REG_ID:            return DEVICE_ID;
    case REG_FW:            return FW_VERSION;
    case REG_DYN:           return (uint8_t)(val_dyn >> 16);
    case REG_DYN + 1:       return (uint8_t)(val_dyn >> 8);
    case REG_DYN + 2:       return (uint8_t)val_dyn;
    case REG_STATIC:        return (uint8_t)(val_static >> 16);
    case REG_STATIC + 1:    return (uint8_t)(val_static >> 8);
    case REG_STATIC + 2:    return (uint8_t)val_static;
    case REG_PULSES: {
        uint16_t c = pulse_cnt;
        pulse_cnt = 0;
        pulse_latch_lo = (uint8_t)c;
        return (uint8_t)(c >> 8);
    }
    case REG_PULSES + 1:    return pulse_latch_lo;
    case REG_LP_MODE:       return cfg.lp_mode;
    case REG_ADDR:          return cfg.addr;
    case REG_HV:            return hv_enable;
    case REG_SENS:          return (uint8_t)cfg.sens;
    case REG_SENS + 1:      return (uint8_t)(cfg.sens >> 8);
    case REG_LED:           return cfg.led;
    case REG_PERIOD:        return (uint8_t)cfg.period;
    case REG_PERIOD + 1:    return (uint8_t)(cfg.period >> 8);
    case REG_MEASURE:       return (uint8_t)cfg.measure;
    case REG_MEASURE + 1:   return (uint8_t)(cfg.measure >> 8);
    case REG_WARMUP:        return cfg.warmup;
    case REG_STATUS:
        return (phase != PH_OFF ? 0x01 : 0) | (phase == PH_MEASURE ? 0x02 : 0) |
               (filled == STATIC_WINDOW_S ? 0x04 : 0) | (cycling() ? 0x08 : 0);
    case REG_WINDOW_S:      return filled;
    case REG_PHASE_LEFT:    return (uint8_t)phase_left;
    case REG_PHASE_LEFT + 1:return (uint8_t)(phase_left >> 8);
    default:                return 0;
    }
}

static void reg_write(uint8_t r, uint8_t d)
{
    switch (r) {
    case REG_LP_MODE:
        if (d > 1) return;
        cfg.lp_mode = d;
        break;
    case REG_ADDR:
        if (d < 0x03 || d > 0x77) return;
        cfg.addr = d;
        break;
    case REG_HV:
        if (d <= 1) hv_enable = d;
        return;                          /* not persistent */
    case REG_SENS:
        cfg.sens = (cfg.sens & 0xFF00) | d;
        values_dirty = true;
        break;
    case REG_SENS + 1:
        cfg.sens = (cfg.sens & 0x00FF) | ((uint16_t)d << 8);
        values_dirty = true;
        break;
    case REG_LED:
        if (d > 1) return;
        cfg.led = d;
        break;
    case REG_PERIOD:        cfg.period  = (cfg.period & 0xFF00) | d; break;
    case REG_PERIOD + 1:    cfg.period  = (cfg.period & 0x00FF) | ((uint16_t)d << 8); break;
    case REG_MEASURE:       cfg.measure = (cfg.measure & 0xFF00) | d; break;
    case REG_MEASURE + 1:   cfg.measure = (cfg.measure & 0x00FF) | ((uint16_t)d << 8); break;
    case REG_WARMUP:        cfg.warmup = d; break;
    default:
        return;
    }
    cfg_dirty = 1;
}

/* ---- TWI client -------------------------------------------------------- */
static void twi_init(void)
{
    TWI0.SCTRLA = 0;
    /* erratum: PORT output bits must be 0 or the TWI cannot pull the lines low */
    PORTB.DIRCLR = PIN0_bm | PIN1_bm;
    PORTB.OUTCLR = PIN0_bm | PIN1_bm;
    TWI0.SADDR = cfg.addr << 1;
    TWI0.SADDRMASK = 0;
    TWI0.SSTATUS = TWI_DIF_bm | TWI_APIF_bm | TWI_COLL_bm | TWI_BUSERR_bm;
    TWI0.SCTRLA = TWI_DIEN_bm | TWI_APIEN_bm | TWI_PIEN_bm | TWI_ENABLE_bm;
    twi_busy = 0;
    twi_busy_ticks = 0;
}

ISR(TWI0_TWIS_vect)
{
    uint8_t st = TWI0.SSTATUS;

    if (st & (TWI_COLL_bm | TWI_BUSERR_bm)) {
        TWI0.SSTATUS = TWI_DIF_bm | TWI_APIF_bm | TWI_COLL_bm | TWI_BUSERR_bm;
        twi_busy = 0;
        return;
    }

    if (st & TWI_APIF_bm) {
        if (st & TWI_AP_bm) {                       /* our address (start / repeated start) */
            twi_busy = 1;
            twi_busy_ticks = 0;
            twi_first = true;
            twi_tx_started = false;
            if (values_dirty)
                recompute();                        /* SCL is stretched meanwhile (<1 ms) */
            TWI0.SCTRLB = TWI_SCMD_RESPONSE_gc;     /* ACK */
        } else {                                    /* stop */
            TWI0.SSTATUS = TWI_APIF_bm;
            twi_busy = 0;
        }
        return;
    }

    if (st & TWI_DIF_bm) {
        if (st & TWI_DIR_bm) {                      /* host reads */
            if (twi_tx_started && (st & TWI_RXACK_bm)) {
                TWI0.SCTRLB = TWI_SCMD_COMPTRANS_gc;    /* host NACKed: done */
            } else {
                twi_tx_started = true;
                TWI0.SDATA = reg_read(reg_ptr++);
                TWI0.SCTRLB = TWI_SCMD_RESPONSE_gc;
            }
        } else {                                    /* host writes */
            uint8_t d = TWI0.SDATA;
            if (twi_first) {
                reg_ptr = d;
                twi_first = false;
            } else {
                reg_write(reg_ptr++, d);
            }
            TWI0.SCTRLB = TWI_SCMD_RESPONSE_gc;     /* ACK */
        }
    }
}

/* ---- Geiger pulse ------------------------------------------------------ */
ISR(PORTA_PORT_vect)
{
    uint8_t f = PORTA.INTFLAGS;
    PORTA.INTFLAGS = f;
    if ((f & PULSE_bm) && phase == PH_MEASURE) {
        if (cur_bin != 0xFFFF)
            cur_bin++;
        if (pulse_cnt != 0xFFFF)
            pulse_cnt++;
        if (cfg.led) {
            PORTA.OUTSET = LED_bm;
            led_on = 1;
        }
    }
}

/* ---- 1 Hz tick --------------------------------------------------------- */
ISR(RTC_PIT_vect)
{
    RTC.PITINTFLAGS = RTC_PI_bm;
    tick_flag = 1;

    /* never let a broken transaction block the host's I2C bus */
    if (twi_busy) {
        if (++twi_busy_ticks >= 3)
            twi_init();
    } else {
        twi_busy_ticks = 0;
    }
    phase_tick();
}

/* ---- init -------------------------------------------------------------- */
static void clock_init(void)
{
    /* 20 MHz internal oscillator / 4 = 5 MHz */
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLB, CLKCTRL_PDIV_4X_gc | CLKCTRL_PEN_bm);
}

static void rtc_init(void)
{
#if USE_XTAL32K
    _PROTECTED_WRITE(CLKCTRL.XOSC32KCTRLA,
                     CLKCTRL_CSUT_1K_gc | CLKCTRL_RUNSTDBY_bm | CLKCTRL_ENABLE_bm);
    while (RTC.STATUS) {}
    RTC.CLKSEL = RTC_CLKSEL_TOSC32K_gc;
#else
    while (RTC.STATUS) {}
    RTC.CLKSEL = RTC_CLKSEL_INT32K_gc;
#endif
    /* some silicon revisions only run the PIT while the RTC itself is enabled */
    RTC.CTRLA = RTC_PRESCALER_DIV1_gc | RTC_RTCEN_bm;
    RTC.PITINTCTRL = RTC_PI_bm;
    while (RTC.PITSTATUS) {}
    RTC.PITCTRLA = RTC_PERIOD_CYC32768_gc | RTC_PITEN_bm;   /* 1 s */
}

static void gpio_init(void)
{
    PORTA.OUTCLR = LED_bm | GEIGER_EN_bm;
    PORTA.DIRSET = LED_bm | GEIGER_EN_bm;
    /* unused pins and the (not yet active) pulse input: digital buffer off */
    PORTA.PIN1CTRL = PORT_ISC_INPUT_DISABLE_gc;
    PORTA.PIN2CTRL = PORT_ISC_INPUT_DISABLE_gc;
    PORTA.PIN3CTRL = PORT_ISC_INPUT_DISABLE_gc;
    PORTA.PIN7CTRL = PORT_ISC_INPUT_DISABLE_gc;
    PULSE_PINCTRL  = PORT_ISC_INPUT_DISABLE_gc;
    PORTB.PIN2CTRL = PORT_ISC_INPUT_DISABLE_gc;
    PORTB.PIN3CTRL = PORT_ISC_INPUT_DISABLE_gc;
}

int main(void)
{
    clock_init();
    _PROTECTED_WRITE(WDT.CTRLA, WDT_PERIOD_8KCLK_gc);      /* 8 s watchdog */
    gpio_init();
    cfg_load();

    /* I2C first: the host scans the bus right after power-up and must find us */
    twi_init();
    rtc_init();
    enter_warmup();                     /* GGreg20 on, counting starts after warm-up */
    sei();

    /* RadSens blinks at start-up, so do we (I2C is already being served) */
    for (uint8_t i = 0; i < 3; i++) {
        PORTA.OUTSET = LED_bm;
        _delay_ms(40);
        PORTA.OUTCLR = LED_bm;
        _delay_ms(120);
    }

    for (;;) {
        if (tick_flag) {
            tick_flag = 0;
            wdt_reset();
        }
        if (led_on) {
            _delay_us(LED_FLASH_US);
            cli();
            PORTA.OUTCLR = LED_bm;
            led_on = 0;
            sei();
        }
        if (cfg_dirty && !twi_busy)
            cfg_save();

        cli();
        if (!tick_flag && !led_on && !(cfg_dirty && !twi_busy)) {
            /* while a transaction is open only IDLE keeps the TWI data
             * interrupts alive; otherwise power-down (wake: pulse, PIT,
             * I2C address match) */
            SLPCTRL.CTRLA = (twi_busy ? SLPCTRL_SMODE_IDLE_gc : SLPCTRL_SMODE_PDOWN_gc) |
                            SLPCTRL_SEN_bm;
            sei();
            sleep_cpu();
        }
        sei();
    }
}
