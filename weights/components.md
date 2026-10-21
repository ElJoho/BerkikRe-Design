# Berkirk 3 components and measured masses (weighed 2026-10-16)

Kitchen scale (Texon, 7000 g × 1 g). Photo names are `20261016_<number>.jpg` in this folder. QR codes were decoded with OpenCV where possible; most are too small or angled to read.

| # | Component | Reference / model | URL | Weight (g) | Photos |
|---|---|---|---|---|---|
| 1 | Flight controller | Pixhawk PRO, B-Cube | — | **40** | 164948, 164949 |
| 2 | ESC | Hobbywing Skywalker 60A V2-UBEC (3–6S, SBEC 5 V/7 A) | Manual QR = facebook.com/qr?id=100063637749362 (only their Facebook page) | **56** | 172121, 172122, 172141 (manual, no weight) |
| 3 | FPV camera | Razer Mini V3 Analog Camera, code **HS1275**, 5–25 V input | http://qr61.cn/opqdTW/q8L2BWk (box side label "Manual HS1268 HS1275") | **12** | 172232, 172312, 172315 (box); 172344, 172346, 172359, 172404 |
| 4 | Servo (elevon) | MG90D (metal gear micro servo) | — | **14** (each) | 172507, 172515 (with horns/screws bag) |
| 5 | Power lead | XT60H male/female pigtail, 12 AWG, bag of 5 | — | **18** (one); 89–90 (bag of 5) | 172554 (label), 172606, 172611, 172643 |
| 6 | USB-C extension board for the Pixhawk | bag labelled "PRO 2026/05/08" | — | **4** | 172939 (bag), 172956, 173214 |
| 7 | LED-USB board | "LED-USB" (I2C + USB) | — | **5** | 173227 |
| 8 | Safety switch + buzzer | "Beep And Safety V1.2" (button + buzzer + harness) | — | **10** | 173340, 173343, 173350, 173351 |
| 9 | microSD card | 4 GB TF card, already inside the Pixhawk (from the bag note) | — | not weighed separately | 173343 (bag note) |
| 10 | PPM encoder | "PPM Encoder", V1.0, ATmega328PB | — | **2** | 173511 (chip side), 173519 (label side) |
| 11 | Receiver | RadioMaster, 2-antenna diversity receiver (model not legible) | radiomasterrc.com/pages/user-manuals, radiomasterrc.com/pages/firmware-updates (printed on the card) | **3–4** | 173828, 173838, 173839, 173842, 173849, 173901 |
| 12 | OLED display | "OLED for Pixhawk" | — | **5** (inside its plastic box) | 173051 |
| 13 | Video transmitter | RushFPV Max Solo | — | **11 or 17** (unclear) | 174919, 174934, 174935 |
| 14 | Battery | Veranty LiPo 6000 mAh 60C (max 80C), XT60 | — | **367** | 175429 |

## Not identified or not readable
- **Receiver (#11):** the photos show it's RadioMaster, but the model name isn't legible. Check the box or the board.
- **VTX (#13) weight:** in 174919, 174934 and 174935 the display is at an angle and blurry. It reads 17 or 11, and it was weighed inside its bag.
- **Battery (#14) cell count:** the label only shows the generic list (1 cell = 3.7 V … 6 cells = 22.2 V). The S rating isn't visible in 175429.
- **Readings that don't match the rest:**
  - 172346 shows **0** with the camera on the scale (the other two camera photos say 12).
  - 173842 shows **6** for the receiver (the others say 3–4; your hand or the card may have been touching the scale).
  - 173828 shows **3** and 173838 shows **4**, so the receiver is 3 or 4 g.
- **Weighed with packaging:** the OLED (#12, plastic box) and the VTX (#13, bag), so their real weights are a bit lower.
- **No weight visible:** 172141 (ESC manual), the camera boxes, 172939 and 172956 (USB board). They're just reference photos.
- **Same part, both sides:** 173511 and 173519 are the PPM encoder. 173340 and 173350 are the safety switch. Each is counted once.

**Total of one of each** (2 servos, 1 XT60 lead, VTX as 17 g, without the OLED): **≈ 551 g**.

