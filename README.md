# VRHandMouse

## Descriere

**VRHandMouse** este o aplicație Windows pentru controlul cursorului și al unor interacțiuni avansate folosind gesturi ale mâinii detectate prin cameră web. Proiectul folosește **Python**, **OpenCV** și **MediaPipe** pentru urmărirea în timp real a mâinilor și transformarea gesturilor în comenzi de mouse.

Aplicația este gândită pentru rulare locală, cu interfață minimă, calibrare fullscreen, icon în **system tray** și mod de lucru orientat către utilizare practică, fără a depinde de o instalare separată de Python pentru varianta distribuită.

![Logo VRHandMouse](icon.png)

## Prezentare vizuală

```mermaid
flowchart LR
    A[Camera web] --> B[MediaPipe Hands]
    B --> C[Detectare gesturi]
    C --> D[Cursor & click]
    C --> E[Scroll]
    C --> F[3D / Zoom]
    C --> G[Tray control]
```

```mermaid
flowchart TD
    A[Pornire aplicație] --> B[Calibrare fullscreen]
    B --> C[Fereastră ghid gesturi]
    C --> D[Emulare dezactivată]
    D --> E[Triunghi]
    E --> F[Emulare activă]
```

## Funcționalități principale

- 🎯 calibrare fullscreen cu ținte în colțuri și centru;
- 🖱️ control cursor prin poziția degetului arătător;
- 👆 click stânga, dublu-click și drag;
- 👉 click dreapta;
- 🔺 activare / dezactivare emulare prin gest de **triunghi**;
- ↕️ scroll prin gest dedicat;
- 🧩 mod **3D / zoom** prin gest dedicat cu două mâini;
- 🪟 ghid vizual de gesturi după calibrare;
- 📌 icon în tray cu stare, cameră și închidere;
- 🔒 protecție de **instanță unică**;
- 📦 pachet distribuit sub formă de executabil SFX.

## Gesturi

| Pictogramă | Gest | Acțiune |
| --- | --- | --- |
| 🔺 | triunghi cu ambele mâini | activare / dezactivare emulare |
| 👆 | mare + arătător | click / drag |
| 👉 | mare + deget mic dreapta | click dreapta |
| ↕️ | mare + mijlociu dreapta | scroll |
| 🧩 | mare + inelar pe ambele mâini | mod 3D / zoom |

### În calibrare

- **Mișcare cursor:** poziția degetului arătător
- **Click pe ținte:** pinch scurt între **degetul mare** și **arătător**
- **Ieșire:** butonul **EXIT**

### În utilizare

- **Activare / dezactivare emulare:** triunghi cu ambele mâini
- **Click stânga / drag:** **deget mare + arătător**
- **Click dreapta:** **deget mare + deget mic** pe mâna dreaptă
- **Scroll:** **deget mare + deget mijlociu** pe mâna dreaptă
- **Mod 3D / zoom:** **deget mare + inelar** pe ambele mâini

## Cerințe

- Windows
- cameră web funcțională

Pentru dezvoltare locală, proiectul folosește:

- Python 3.10
- MediaPipe
- OpenCV
- psutil

## Rulare în dezvoltare

Din rădăcina proiectului:

```bat
vr_tools.bat
```

Acest script verifică mediul local, dependențele și pornește `vision_tracker.py`.

## Executabil distribuit

În proiect există și o variantă distribuită ca executabil SFX, construită din folderul `dist\VRHandController`, astfel încât utilizatorul final să poată porni aplicația fără instalare separată de Python.

## Structura proiectului

- `vision_tracker.py` - aplicația principală de tracking și control gestual
- `vr_tools.bat` - launcher local pentru dezvoltare
- `icon.ico` / `icon.png` - resurse grafice
- `screen-metrics/` - utilitar auxiliar pentru măsurători de ecran
- `dist\` - artefacte generate pentru distribuție

## Observații

- aplicația este optimizată pentru un flux de lucru Windows;
- în lipsa camerei sau la erori de acces, controlul se poate gestiona din tray;
- pentru distribuție se recomandă utilizarea executabilului SFX generat.
