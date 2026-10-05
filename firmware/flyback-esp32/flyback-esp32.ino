/*
  flyback-esp32 — o firmware dos flybacks para o site flyback-midi.

  Recebe pela serial o protocolo de docs/protocolo-serial.md (P, R, N, F, X) e toca cada canal
  como onda quadrada na frequência da nota, num GPIO que interrompe o oscilador do flyback.

  Testado com: ESP32 comum ("ESP32 Dev Module" no Arduino). Compila também para o ESP32-S3,
  mas lá só os canais 1 a 4 tocam — ver CANAIS abaixo.

  Antes de gravar, confira LOGICA_INVERTIDA para o seu circuito.
*/
#include <Arduino.h>
#include "driver/ledc.h"

// ------------------------------------------------------------------ ajuste para o seu circuito

// true:  GPIO em ALTO CORTA o arco. É o circuito com um NPN aterrando o pino 4 (reset) do 555:
//        com o pino em ALTO o transistor conduz e o 555 para; com o pino em BAIXO, ou sem sinal
//        nenhum, o 555 oscila e o arco fica ligado.
// false: GPIO em ALTO LIBERA o arco.
// A polaridade fica aqui, e não na página, porque o silêncio tem de estar certo também quando a
// página não está conectada: no boot, com o navegador fechado, com a aba travada.
const bool LOGICA_INVERTIDA = true;

const uint32_t BAUD = 115200;        // o mesmo escolhido na página (115200 é o padrão dela)

// Pinos de cada canal até a página mandar o mapa ("P c g"). São os padrões da página, para o
// firmware já funcionar se as primeiras linhas se perderem: muitas placas reiniciam quando a
// porta serial é aberta, e o que chega durante o boot some.
#if CONFIG_IDF_TARGET_ESP32S3
const int PINOS_PADRAO[6] = {4, 5, 6, 7, 15, 16};
#else
const int PINOS_PADRAO[6] = {18, 19, 21, 22, 23, 25};
#endif

// Nota que passa disso sem nenhum evento novo no canal é cortada: se o navegador travar no
// meio de uma nota, o "F" dela nunca chega, e o arco não pode ficar ligado para sempre.
const uint32_t NOTA_MAXIMA_MS = 20000;

// ------------------------------------------------------------------ geração do tom (LEDC)
// Cada canal tem um timer só dele, para cada um ter a sua frequência. O ESP32 comum tem 4
// timers rápidos e 4 lentos: os 6 canais cabem. O S3 tem 4 timers: 4 canais.
#ifdef SOC_LEDC_SUPPORT_HS_MODE
const int CANAIS = 6;
static ledc_mode_t modoDe(int c) { return c < 4 ? LEDC_HIGH_SPEED_MODE : LEDC_LOW_SPEED_MODE; }
#else
const int CANAIS = 4;
static ledc_mode_t modoDe(int c) { (void)c; return LEDC_LOW_SPEED_MODE; }
#endif
static ledc_timer_t timerDe(int c) { return (ledc_timer_t)(c % 4); }
static ledc_channel_t canalDe(int c) { return (ledc_channel_t)c; }

// 13 bits: com o relógio de 80 MHz o divisor do LEDC vai até 1024, então a faixa é de 9,5 Hz
// a 9,7 kHz. Com 10 bits nada abaixo de 76 Hz sairia — o baixo inteiro.
const ledc_timer_bit_t RESOLUCAO = LEDC_TIMER_13_BIT;
const uint32_t CHEIO = 1u << 13;              // duty de 100%: saída parada em ALTO
const uint32_t METADE = CHEIO / 2;            // onda quadrada
const uint32_t SILENCIO = LOGICA_INVERTIDA ? CHEIO : 0;

// ------------------------------------------------------------------ filas
struct Evento { uint32_t quando; float f; };   // f = 0: silêncio
const int FILA = 96;
struct Canal {
  int pino = -1;
  bool soando = false;
  uint32_t desde = 0;
  Evento fila[FILA];
  int n = 0;
};
static Canal canal[6];
static uint32_t t0 = 0;                        // o instante do último "R"
static uint32_t perdidos = 0;                  // eventos que não couberam na fila

static void pinoSeguro(int g) {                // pino solto do LEDC, parado no silêncio
  pinMode(g, OUTPUT);
  digitalWrite(g, LOGICA_INVERTIDA ? HIGH : LOW);
}

static void duty(int c, uint32_t d) {
  ledc_set_duty(modoDe(c), canalDe(c), d);
  ledc_update_duty(modoDe(c), canalDe(c));
}

static void silencia(int c) {
  if (canal[c].pino < 0) return;
  duty(c, SILENCIO);
  canal[c].soando = false;
}

static void toca(int c, float f) {
  if (canal[c].pino < 0) return;
  uint32_t hz = (uint32_t)lroundf(f);
  if (hz < 10 || ledc_set_freq(modoDe(c), timerDe(c), hz) != ESP_OK) { silencia(c); return; }
  duty(c, METADE);   // 50%: tanto faz a polaridade, o arco liga e desliga na frequência da nota
  canal[c].soando = true;
  canal[c].desde = millis();
}

static int donoDoPino(int g, int fora) {
  for (int i = 0; i < 6; i++) if (i != fora && canal[i].pino == g) return i;
  return -1;
}

// "P c g": o canal c passa a acionar o GPIO g; g = -1 libera o canal
static void fixaPino(int c, int g) {
  if (c < 0 || c > 5) return;
  Canal &k = canal[c];
  if (k.pino == g) return;                     // a página manda o mapa inteiro de novo: nada muda
  if (k.pino >= 0) {
    silencia(c);
    if (donoDoPino(k.pino, c) < 0) pinoSeguro(k.pino);
  }
  k.pino = -1; k.n = 0; k.soando = false;
  if (g < 0) return;
  if (c >= CANAIS) {
    Serial.printf("canal %d: esta placa só tem timer para %d canais\n", c + 1, CANAIS);
    pinoSeguro(g);
    return;
  }
  int outro = donoDoPino(g, c);                // dois canais no mesmo pino: fica o último
  if (outro >= 0) { silencia(outro); canal[outro].pino = -1; canal[outro].n = 0; }

  ledc_timer_config_t tc = {};
  tc.speed_mode = modoDe(c);
  tc.duty_resolution = RESOLUCAO;
  tc.timer_num = timerDe(c);
  tc.freq_hz = 440;
  tc.clk_cfg = LEDC_AUTO_CLK;
  ledc_channel_config_t cc = {};
  cc.gpio_num = g;
  cc.speed_mode = modoDe(c);
  cc.channel = canalDe(c);
  cc.intr_type = LEDC_INTR_DISABLE;
  cc.timer_sel = timerDe(c);
  cc.duty = SILENCIO;
  cc.hpoint = 0;
  if (ledc_timer_config(&tc) != ESP_OK || ledc_channel_config(&cc) != ESP_OK) {
    Serial.printf("canal %d: o GPIO %d não serve de saída\n", c + 1, g);
    return;
  }
  k.pino = g;
  duty(c, SILENCIO);
}

// insere mantendo a fila em ordem de tempo; a página manda quase sempre em ordem
static void enfileira(int c, uint32_t quando, float f) {
  if (c < 0 || c > 5 || canal[c].pino < 0) return;
  Canal &k = canal[c];
  if (k.n >= FILA) { perdidos++; return; }
  int i = k.n;
  while (i > 0 && (int32_t)(k.fila[i - 1].quando - quando) > 0) { k.fila[i] = k.fila[i - 1]; i--; }
  k.fila[i] = {quando, f};
  k.n++;
}

static void executa() {
  uint32_t agora = millis();
  for (int c = 0; c < 6; c++) {
    Canal &k = canal[c];
    while (k.n && (int32_t)(agora - k.fila[0].quando) >= 0) {
      Evento e = k.fila[0];
      for (int i = 1; i < k.n; i++) k.fila[i - 1] = k.fila[i];
      k.n--;
      if (e.f > 0) toca(c, e.f); else silencia(c);
    }
    if (k.soando && !k.n && agora - k.desde > NOTA_MAXIMA_MS) silencia(c);
  }
}

static void trata(char *s) {
  int c, g; long t; float f;
  switch (s[0]) {
    case 'P': if (sscanf(s + 1, "%d %d", &c, &g) == 2) fixaPino(c, g); break;
    case 'R': t0 = millis(); for (int i = 0; i < 6; i++) canal[i].n = 0; break;
    case 'X': for (int i = 0; i < 6; i++) { silencia(i); canal[i].n = 0; } break;
    case 'N': if (sscanf(s + 1, "%d %ld %f", &c, &t, &f) == 3 && t >= 0) enfileira(c, t0 + (uint32_t)t, f); break;
    case 'F': if (sscanf(s + 1, "%d %ld", &c, &t) == 2 && t >= 0) enfileira(c, t0 + (uint32_t)t, 0); break;
    case '?':                                  // para conferir pelo monitor serial
      Serial.printf("lógica %s · %d canais · pinos", LOGICA_INVERTIDA ? "invertida" : "direta", CANAIS);
      for (int i = 0; i < 6; i++) Serial.printf(" %d", canal[i].pino);
      Serial.printf(" · eventos perdidos %lu\n", (unsigned long)perdidos);
      break;
  }
}

void setup() {
  // primeiro de tudo, antes até da serial: os pinos no silêncio, arco cortado
  for (int i = 0; i < 6; i++) pinoSeguro(PINOS_PADRAO[i]);
  Serial.begin(BAUD);
  for (int i = 0; i < CANAIS; i++) fixaPino(i, PINOS_PADRAO[i]);
  Serial.printf("flyback-esp32 pronto · lógica %s · %d canais\n",
                LOGICA_INVERTIDA ? "invertida (ALTO corta o arco)" : "direta (ALTO libera o arco)", CANAIS);
}

void loop() {
  static char linha[64];
  static int tam = 0;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n') { linha[tam] = 0; trata(linha); tam = 0; }
    else if (ch != '\r' && tam < (int)sizeof(linha) - 1) linha[tam++] = ch;
  }
  executa();
}
