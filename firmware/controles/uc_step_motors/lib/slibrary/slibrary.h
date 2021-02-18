/*
  * uc_step_motor
  *======================
  * RESET, DIR SETUP
  * rst3, dir2: rst3 is myph_a (acido), dir2 is for two bombs
  * rst1, dir1: myfeed
  * rst4, dir456: unload  (dir4 para unload, no se usa)
  * rst2, dir456: mymix
  * rst5, dir3: mytemp
  * rst6, dir6: rst6 is myph_b, dir2 is for two bombs  dir6 is FREE !


    write by: Felipe Hooper
    Electronic Engineer
*/


#include "Arduino.h"


#define MIN_to_us 60e6 //60e6   [us]
#define STEPS     200 //200  [STEPS]
#define TIME_T    20  //TIME_T [us]

#define TIME_MIN  2000  //se despeja de SPEED_MAX
#define SPEED_MAX 150   //MIN_to_us/(STEPS*TIME_MIN)
#define SPEED_MIN 1
#define TEMP_MAX  130

#define CONVERTION(x) ((unsigned int) (MIN_to_us/STEPS/TIME_T) / x) //x = speed [rpm] => Number of counts
#define LIMIT         (TIME_MIN / (2 * TIME_T) )

#define  INT(x) (x-48)  //ascii convertion
#define iINT(x) (x+48)  //inverse ascii convertion

//CHANGE IN FUNCTION THE UCONTROLLER, PORT AND PINS USED.
#define MOT1 PORTB
#define MOT2 PORTB
#define MOT3 PORTB
#define MOT4 PORTB
#define MOT5 PORTB

#define START1 PB0  //ph1
#define START2 PB1  //ph2
#define START3 PB2  //feed
#define START4 PB3  //unload
#define START5 PB4  //temp

#define PORT_CONTROL  PORTD
#define START_CONTROL PD3

//PH: las dos bombas de ph usan el mismo rst y dir
//#define RST_PH     PD4  //pc0 no funciona, PLOP! probe dos micros
#define RST_PHa    PD4
#define RST_PHb    PD5
#define DIR_PH     PC1

#define RST_FEED   PC2
#define DIR_FEED   PC3

#define RST_UNLOAD PC4
//unload no necesita DIR

#define RST_TEMP   PC5
#define DIR_TEMP   PB5

volatile uint16_t count_m1_set = 0;
volatile uint16_t count_m2_set = 0;
volatile uint16_t count_m3_set = 0;
volatile uint16_t count_m4_set = 0;
volatile uint16_t count_m5_set = 0;

uint16_t count_m1 = 0;
uint16_t count_m2 = 0;
uint16_t count_m3 = 0;
uint16_t count_m4 = 0;
uint16_t count_m5 = 0;

uint8_t rst1 = 0;  uint8_t rst2 = 0;  uint8_t rst3 = 0;
uint8_t rst4 = 0;  uint8_t rst5 = 0;  uint8_t rst6 = 0;

uint8_t rsta = 1;  uint8_t rstb = 1;

//DIRECTION SETUP
uint8_t dir1 = 1;  uint8_t dir2 = 1;  uint8_t dir3 = 1;
uint8_t dir4 = 1;  uint8_t dir5 = 1;  uint8_t dir6 = 1;

char    ph_select = 0;
char  temp_select = 0;

uint8_t myph      = 0;
uint8_t myph_a    = 0;
uint8_t myph_b    = 0;
uint8_t myph_a_save = 0;
uint8_t myph_b_save = 0;


uint8_t myfeed   = 0;
uint8_t myunload = 0;
uint8_t mytemp   = 0;


uint8_t myfeed_save   = 0;
uint8_t mytemp_save   = 0;
uint8_t myunload_save = 0;

uint8_t myph1_save    = 0;
uint8_t myph2_save    = 0;

String  message = "";
boolean stringComplete = false;


//_BV(x) = 1 << x
inline void set_motor ( uint16_t *count, uint16_t *count_set, volatile uint8_t *MOT, uint8_t START ) {
  if ( *count == *count_set ) {
    *MOT |= START;
    *count = 0;
  }

  else if ( *count == LIMIT ) {
    *MOT &= ~START;
  }

  (*count)++;
  return;
}

//_BV(x) = 1 << x
//rstx=0 (enable); dirx=1 (cw), else ccw.
inline void setup_dir_rst ( uint8_t RST, uint8_t DIR, uint8_t *var_x, uint8_t *rst_x, uint8_t *dir_x, volatile uint8_t *PORT_1, volatile uint8_t *PORT_2 ) {
  //PORT_1:
  if( !(*rst_x) ) {
    if ( !(*var_x) )
      *PORT_1 &= ~RST;
    else
      *PORT_1 |=  RST;
  }
  else
    *PORT_1 &= ~RST;

  //PORT_2:
  if ( *dir_x )
    *PORT_2 |=  DIR;
  else
    *PORT_2 &= ~DIR;
}


//ISR: Function of Interruption in timer one. _BV(x) = 1 << x
void motor_control() {
  PORT_CONTROL |= (1 << START_CONTROL);     //PIN UP
  set_motor(&count_m1, &count_m1_set, &MOT1, _BV(START1) );
  set_motor(&count_m2, &count_m2_set, &MOT2, _BV(START2) );

  set_motor(&count_m3, &count_m3_set, &MOT3, _BV(START3) );
  set_motor(&count_m4, &count_m4_set, &MOT4, _BV(START4) );
  set_motor(&count_m5, &count_m5_set, &MOT5, _BV(START5) );
  PORT_CONTROL &= ~(1 << START_CONTROL);   //Pin DOWN
}


inline void time_setup ( uint8_t motor_speed, volatile uint16_t *count_set, uint16_t *count ) {
  if ( !motor_speed ) {
    *count = 0;
    *count_set = 0;
    return;
  }
  else {
    *count = 0;
    //Transform of motor_speed [rpm] to time in [us] and SETTING FOR THRESHOLD OF TIME:
    if      ( CONVERTION(motor_speed) <= CONVERTION(SPEED_MAX) )  *count_set = CONVERTION(SPEED_MAX);
    else if ( CONVERTION(motor_speed) >= CONVERTION(SPEED_MIN) )  *count_set = CONVERTION(SPEED_MIN);
    else                                                          *count_set = CONVERTION(motor_speed);

    return;
  }
}


void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    message += inChar;
    if (inChar == '\n') {
      stringComplete = true;
    }
  }
}

//clean strings
void clean_strings() {
  stringComplete = false;
  message    = "";
}


int validate_write() {
  if ( (message[0] == 'a' || message[0] == 'b' || message[0] == 'n' ) && message[11] == 'm' ) return 1;
  else return 0;
}


void crumble() {  //se puede alivianar usando .toFloat() directamente despues de substring
  //setting setpoints
  myfeed   = message.substring(5,8).toInt();
  rst1 = int(INT(message[22]));  //rst_feed
  dir1 = int(INT(message[27]));  //dir_feed


  myunload = message.substring(8,11).toInt();
  rst4 = int(INT(message[25]));  //rst_unload
  dir4 = int(INT(message[30]));  //dir_feed


  mytemp = message.substring(18,21).toInt();
  rst5 = int(INT(message[26]));  //rst_temp
  dir5 = int(INT(message[29]));  //dir_temp
  temp_select = message[17];


  myph      = message.substring(1,4).toInt();
  ph_select = message[0];
  rst3 = int(INT(message[24]));  //rst_ph
  dir2 = int(INT(message[28]));  //rst_ph

  if (rst3 == 0) {
    if ( ph_select == 'a' ) {
        myph_a = myph;
        myph_b = 0;

        rstb = 1; //1=OFF Base bomb
        rsta = 0;
    }
    else if ( ph_select == 'b' ) {
        myph_a = 0;
        myph_b = myph;

        rsta = 1; //1=OFF Acid Bomb
        rstb = 0;
    }
  }

  else if (rst3 == 1) { //rst3 apaga todas las bombas de pH
      rsta = 1;
      rstb = 1;
  }


  //a100f100100m1500tc100r00000111\n


  return;
}
