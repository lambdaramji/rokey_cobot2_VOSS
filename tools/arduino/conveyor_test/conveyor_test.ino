// conveyor_test — 싸이피아 A3 1000 mm 컨베이어 (Arduino Uno + 스텝모터 드라이버)
//
// 배선: D2 → DIR-, D3 → DIR+, D4 → PUL+, PUL- → GND(POWER 영역)
// 업로드하거나 RESET 하면 바로 계속 회전한다. 시리얼 9600 baud: 's' 정지, 'r' 회전.
//
// 속도는 HALF_PERIOD_US(펄스 반주기)로 정한다. 실측표는 docs/measurements-1006.md #1.
//   500 → 2.47 cm/s (원래 스케치 값) · 330 → 3.69 · 250 → 4.89 (개발 설정) · 170 → 6.98 · 110 → 11.01
// 바꾸면 config/voss_config.yaml 의 belt.speed_cmps 도 같이 바꾼다.
//
// 방향을 반대로 하려면 setup() 의 D3 만 LOW 로 바꾼다. D2 를 HIGH 로 하면 벨트가 멈추고
// 핀에 과전류가 흐를 수 있다(10/06 실기).

const int directionNegativePin = 2;
const int directionPositivePin = 3;
const int pulsePositivePin = 4;
const unsigned int HALF_PERIOD_US = 250;
bool isRunning = true;

void setup() {
  Serial.begin(9600);
  pinMode(directionNegativePin, OUTPUT);
  pinMode(directionPositivePin, OUTPUT);
  pinMode(pulsePositivePin, OUTPUT);

  digitalWrite(directionNegativePin, LOW);
  digitalWrite(directionPositivePin, HIGH);
  digitalWrite(pulsePositivePin, LOW);
}

void loop() {
  if (Serial.available()) {
    char command = Serial.read();
    if (command == 's') {
      isRunning = false;
    } else if (command == 'r') {
      isRunning = true;
    }
  }

  if (isRunning) {
    digitalWrite(pulsePositivePin, HIGH);
    delayMicroseconds(HALF_PERIOD_US);
    digitalWrite(pulsePositivePin, LOW);
    delayMicroseconds(HALF_PERIOD_US);
  } else {
    digitalWrite(pulsePositivePin, LOW);
    delay(1);
  }
}
