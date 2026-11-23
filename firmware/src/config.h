/*
 * GGreg20_V3 -> I2C translator (RadSens compatible)
 * Compile-time defaults. Everything marked [EEPROM] can also be changed at
 * runtime over I2C and is then stored in the ATtiny's EEPROM.
 */
#ifndef CONFIG_H
#define CONFIG_H

/* ---- RadSens identity ------------------------------------------------ */
#define I2C_ADDR_DEFAULT        0x66    /* [EEPROM] reg 0x10 */
#define DEVICE_ID               0x7D    /* reg 0x00, checked by Meshtastic */
#define FW_VERSION              0x01    /* reg 0x01 */

/* ---- Tube ------------------------------------------------------------ */
/* Sensitivity in pulses per uR (RadSens "Pavg").
 *   SBM-20: 105   (= 0.0057 uSv/h per CPM)
 *   J305  :  74   (= 0.0081 uSv/h per CPM)                               */
#define SENSITIVITY_DEFAULT     105     /* [EEPROM] reg 0x12/0x13 */

/* ---- Indicator LED on the translator board --------------------------- */
#define LED_DEFAULT             1       /* [EEPROM] reg 0x14, RadSens default = 1 */
#define LED_FLASH_US            300     /* flash length per pulse */

/* ---- Power saving: duty cycling of the GGreg20 supply ---------------- */
/* The GGreg20_V3 draws 35..57 mA while it is powered. In low-power mode the
 * translator switches it on only for MEASURE seconds every PERIOD seconds
 * (plus WARMUP seconds for the HV converter before counting starts).
 * LP_MODE 0 = GGreg20 always on (behaves like a real RadSens).             */
#define LP_MODE_DEFAULT         1       /* [EEPROM] reg 0x0C */
#define CYCLE_PERIOD_DEFAULT    600     /* [EEPROM] reg 0x20/0x21, seconds */
#define MEASURE_TIME_DEFAULT    60      /* [EEPROM] reg 0x22/0x23, seconds */
#define WARMUP_DEFAULT          15      /* [EEPROM] reg 0x24, seconds */

/* ---- Measurement windows (in seconds of *measuring* time) ------------ */
#define STATIC_WINDOW_S         220     /* reg 0x06: fixed sliding window (max 255) */
#define DYNAMIC_WINDOW_MAX_S    123     /* reg 0x03: upper limit of dynamic window */
#define DYNAMIC_TARGET_COUNTS   50      /* dynamic window shrinks to hold ~this many pulses */

/* ---- Hardware options ------------------------------------------------ */
/* 1 = enable the ATtiny's internal pull-up on the pulse input. Only needed
 * if the GGreg20 output turns out to be open-drain without its own pull-up. */
#define PULSE_PULLUP            0
/* 1 = 32.768 kHz crystal Y1 fitted (accurate time base, +~0.5 uA).
 * 0 = internal ULP oscillator (typ. a few % error over temperature).      */
#define USE_XTAL32K             0

#endif
