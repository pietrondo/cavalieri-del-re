# Cavalieri del Re

Gioco 2D in Python e pygame. **Nel repository non c'è nessuna immagine**: ogni
personaggio, ogni oggetto di scena e ogni sfondo sono descritti in Python come
gerarchie di ossa e vengono disegnati a runtime.

## Il livello 1: la fuga da Castel Rosso

Un cavaliere esce dal cortile di un castello medievale e deve arrivare al
bosco. Le guardie del re lo cercano, i cavalieri nemici chiudono la strada e
lungo il cammino ci sono sacchetti di provviste da raccogliere.

- **In sella** si corre; con `MAIUSC` si galoppa e l'attacco diventa una
  stoccata di lancia, più lunga e più dannosa della spada.
- **A piedi** si salta e si mena la spada, e si gira più stretti tra gli
  ostacoli.
- **La discesa e la risalita** sono un'animazione vera, non un teletrasporto:
  `E` quando sei in sella ti porta a terra, `E` di nuovo quando sei vicino al
  cavallo per rimontare.
- **Powerup**: cuore (vita), scudo (blocca un colpo), oro.

Gli incontri sono pianificati a mano in `game.py` con una tabella
`(secondo, tipo)`: lo stesso livello si gioca uguale ogni volta, quindi si può
imparare a memoria.

## Comandi

| Tasto | Azione |
| --- | --- |
| `A` / `D` | muovi a destra o a sinistra |
| `W` | salta (a piedi) |
| `SPAZIO` | attacca: stoccata di lancia in galoppo, fendente di spada a piedi |
| `MAIUSC` + `A`/`D` | galoppo (solo in sella, e serve un movimento laterale) |
| `E` | scendi a terra / rimonta sul cavallo |
| `F` | schermo intero |
| `R` | ricomincia (dopo la vittoria o la sconfitta) |
| `ESC` | esci |

## Come si esegue

Serve Python 3.11 o successivo e pygame 2.x.

```bash
pip install pygame
python game.py
```

Oppure, con i requisiti dichiarati:

```bash
pip install -r requirements.txt
python game.py
```

Ci sono quattro strumenti in `tools/`, tutti headless (nessuna finestra):

```bash
python tools/preview.py     # foglio di contatto degli scheletri, fase per fase
python tools/frames.py      # fotogrammi di gioco veri, in quattro punti del livello
python tools/silhouette.py  # colore, silhouette, grigi e miniatura 32px di ogni attore
python tools/smoke.py       # guida il livello 1 senza finestra e controlla gli invarianti
```

`preview.py` serve a **guardare** gli scheletri mentre li si costruisce: senza
quello si disegna a occhi chiusi. `frames.py` mostra la scena composta, quindi
è l'unico modo per accorgersi che una figura è troppo piccola o che affonda nel
fondo. `silhouette.py` è il controllo di **leggibilità**: lo stesso attore
riempito di nero deve restare riconoscibile, in grigio deve mostrare il
contrasto di valore, e a 32 pixel di altezza deve ancora leggersi. Se la
silhouette non si capisce, nessun dettaglio la salverà. `smoke.py` è il test:
percorre il livello, scende e risale da cavallo, gira anche a sinistra e
verifica che ogni disegno resti nello schermo e che cavallo e cavaliere restino
allineati.

## Come sono fatti gli sprite

Il punto del progetto è questo: **non esiste un solo file immagine nel
repository**. `sprites.py` contiene il sistema, e quello che ci metti dentro è
codice.

### Posa di riposo in coordinate mondo

Un personaggio non è una lista di frame, è uno scheletro. Ogni scheletro
(`Rig`) parte da una **posa di riposo**: le giunzioni sono scritte in
coordinate mondo, con i piedi a `y = 0` e il corpo rivolto verso `+x`, quindi
si legge come un disegno, non come una tabella di numeri.

Il vantaggio è che la posa di riposo si può scrivere guardando la figura, e non
calcolando coordinate locali a mano di ogni giunto.

### `Builder`: le ossa si incatena da sole

Il `Builder` fa il lavoro aritmetico che altrimenti sarebbe un disastro di
`sin()` e `cos()`. L'idea è che **un arto si aggancia alla punta del proprio
genitore**, quindi non si scrive mai da dove parte:

```python
b = Builder()
b.link("rump", "root", (-42, -66), 0.16, 28, 35, 33, HORSE)
b.limb("barrel", "rump", -0.06, 32, 33, 29, HORSE)   # parte dalla punta di rump
b.limb("chest",  "barrel", -0.10, 20, 29, 23, HORSE)  # parte dalla punta di barrel
```

Con `limb()` la posizione di partenza è il `tip` del padre, calcolata dal `Builder`
stesso. Con `deco()` invece si danno le coordinate mondo, perché le
decorazioni (orecchie, creste, lanterne, selle) possono stare dove vanno e non
devono per forza attaccarsi a qualcosa.

Il risultato è che la cinematica inversa — l'angolo di ogni arto relativo al
padre, sommato lungo la catena per ottenere l'angolo in mondo — è risolta una
volta sola nel `Rig.solve()` e non va riscritta in ogni posa.

### FK: dalla posa alle coordinate

Ogni frame fa tre passi, in quest'ordine:

1. una **posa** è una mappa di angoli relativi per osso (`{"thigh": 0.6,
   "shin": -1.1, ...}`) più un sollevamento del bacino;
2. **`Rig.solve()`** applica quegli offset alla posa di riposo e risolve la
   **forward kinematics** percorrendo le ossa in ordine, accumulando posizione
   e angolo del padre;
3. ogni ossa risolta viene **rasterizzata**.

Il `Rig` controlla anche la posa di riposo all'avvio: un arto che non arriva
esattamente sulla giunzione del figlio fa fallire il costruttore con un
assert, invece di produrre una figura con un braccio staccato dal corpo. Le
catene non possono uscire sbagliate in silenzio.

### Antialiasing senza un pixel di arte

Le superfici vengono disegnate su un buffer **sovracampionato x3** (`SS = 3`)
e poi ridotte con `pygame.transform.smoothscale`. L'antialiasing è il
risultato della riduzione, non un filtro e non un'immagine di partenza: è lo
stesso trucco che si usa per la tipografia vettoriale, applicato alle ossa.

Il disegno stesso è fatto di capsule (un quadrilatero più due cerchi ai capi,
con spessore diverso alla radice e alla punta), poligoni e cerchi, con una
luce unica per tutta la troupe: ogni ossa si auto-illumina dal lato della luce e
prende un riverbero freddo dall'altro. Le ossa della metà lontana del corpo
vengono scurite e desaturate, e la profondità si legge senza alcuna vera
illuminazione. Ogni osso porta un contorno scuro nel proprio colore, e attorno
all'intera silhouette ne viene disegnato un secondo: il primo separa gli arti
tra loro, il secondo stacca l'attore dallo sfondo.

Il colore non è decorazione, è **leggibilità**. Il cavallo è baio scuro e il
cavaliere acciaio chiaro, così in grigio restano due valori distinti e il
cavaliere non si fonde con la groppa; la piuma è il landmark che nella
silhouette rompe la testa. `tools/silhouette.py` è lì per verificarlo.

### Le pose

Le funzioni di posa (`horse_pose`, `rider_pose`) trasformano il tempo in
angoli: ciclo di galoppo con gruppi di fase diversi per zampe anteriori e
posteriori, corsa a due gambe in controfase, risalita a cavallo come blend tra
la posa in sella e quella a piedi, stoccata della lancia in cui entrambe le
braccia vengono allineate per riportare l'asta in orizzontale.

Un rig, quindi, non è un personaggio: è un personaggio potenziale. Le guardie,
i cavalieri nemici e l'eroe sono lo stesso scheletro con parametri diversi
(scala, colori, arma, scudo, cresta, lancia).

## Struttura del progetto

```
cavalieri-del-re/
├── README.md            questo file
├── requirements.txt     pygame>=2.5
├── .gitignore
├── game.py              livello 1: personaggi, combattimento, raccolta, HUD, ciclo principale
├── pickup.py            i provviste sulla strada: cuore, scudo, oro
├── sprites.py           il sistema a scheletro: Bone, Rig, Builder, FK, rasterizzazione e pose
├── world.py             scena: cielo, colline, castello, portone, strada, obiettivo
├── tools/
│   ├── preview.py       foglio di contatto degli scheletri, fase per fase
│   ├── frames.py        fotogrammi di gioco veri, per giudicare la scena
│   └── smoke.py         test: guida il livello headless, controlla gli invarianti
```

## Scala degli attori

Un cavaliere a cavallo è il soggetto dell'inquadratura, quindi occupa circa un
terzo dell'altezza dello schermo. La scala si applica **alla geometria** delle
ossa (non a un ingrandimento dell'immagine, che sfocherebbe): `HORSE_S` e
`HUMAN_S` in `game.py`. Da lì derivano anche l'altezza della sella a cui si
siede il cavaliere (`SEAT`) e la portata delle armi, così le proporzioni
restano coerenti se cambi la scala.

Ogni attore ha un'**ombra di contatto**: un'ellisse schiacciata alla base. Su
uno sfondo crepuscolare uno sprite scuro senza ombra sembra sospeso; con
l'ombra è piantato a terra.