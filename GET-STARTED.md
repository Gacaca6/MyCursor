# MyCursor — use your phone as your computer's mouse

Control a Windows PC from your phone: move the pointer, click, scroll with one
thumb, type, and change slides. No account, no internet, nothing to buy.

## 1. On the computer (once)

1. Download **MyCursor.exe** and double-click it.
2. If Windows says *"Windows protected your PC"*, click **More info → Run anyway**.
   (This appears for new apps that are not yet signed; MyCursor is safe to run.)
3. The MyCursor logo appears while it installs (a few seconds, no questions).
   MyCursor is then in your **Start menu** and on your **desktop**.
4. When Windows asks *"Do you want to allow this app to make changes?"*, click
   **Yes**. This only lets your phone reach MyCursor on your local network.

To update later, download the new **MyCursor.exe** and open it: it replaces
the old version and keeps your phone paired. To remove MyCursor, open
**Settings › Apps › Installed apps**, find **MyCursor** and choose **Uninstall**.

The MyCursor window opens on its **Connect** page, with a big square code (QR
code). The list on the left has a page for everything MyCursor does: **Connect**,
**Share files**, **Offline**, **Bluetooth** and **Settings**. No mouse yet? Press
**Tab** and **Enter**, or **Ctrl+1** to **Ctrl+5** to switch pages.

From now on MyCursor starts by itself whenever you sign in to Windows, with
its offline Wi-Fi already on, so your phone can connect straight away. If it is
ever closed, press **Ctrl+Alt+P** on the keyboard to open it again — no mouse
needed. Closing its window keeps it running in the
taskbar; to stop it, open **Settings** and choose **Quit** (the **Start with
Windows** switch is there too).

## 2. On the phone

1. Make sure the phone is on the **same Wi-Fi** as the computer.
2. Open the **Camera**, point it at the code on the computer, and tap the link.
3. The touchpad opens. To keep it on your Home Screen:
   - **iPhone:** Share button → **Add to Home Screen**.
   - **Android:** Chrome menu **⋮ → Add to Home screen**.

Next time, just open MyCursor on the computer and tap the MyCursor icon on your phone.

## Using it

- **Move:** slide one finger on the big pad. The pointer is Windows' own and
  follows your Windows mouse settings, just like a real mouse. Change the speed
  in the phone's gear button → **Pointer speed**.
- **Click:** tap the pad, or press **Left** / **Right**.
- **Scroll:** swipe the tall wheel at the bottom with your thumb.
- **Drag:** hold **Left** and slide, or tap the hand button.
- **Type:** tap the keyboard button — letters appear on the computer as you type.

The tabs at the top switch modes:

- **Present** (for lectures): a big **Next** button, Back, black screen, a
  **zoom** that follows the pointer (**Zoom 1×** always returns to normal), and
  a talk timer that warns you near the end. With PowerPoint, your **speaker
  notes** show on the phone and slides change even if PowerPoint is not the
  active window. Tap the notes to make the text bigger.
- **Media** (films and music on a TV or projector): play/pause, skip, volume,
  fullscreen, and a **sleep timer** that puts the computer to sleep.
- **Share**: tap **Photos & videos** or **Files** to send them to the computer —
  they land in **Downloads** and a small card offers **Open** or **Show in
  folder**. To send the other way, open **Share files** in the MyCursor
  window and click **Choose files**, or right-click any file on the computer →
  **Send to → MyCursor phone** (on Windows 11: **Show more options** first).
  On the phone, tap **Save**: on iPhone, photos open full screen — press and
  hold, then **Save to Photos**; videos and documents go to the **Files** app.
  On Android everything saves with one tap and photos appear in Gallery.
  If the Wi-Fi drops mid-transfer, sending picks up where it stopped. Paste a
  link and tap **Open link on PC** to open it there. No cable, no internet,
  no mobile data.

## No Wi-Fi? No internet?

On the computer, open **Offline** and click **Start offline Wi-Fi**. Scan the first
code to join the computer's Wi-Fi, then the second code to open the touchpad. It
needs no internet and uses no mobile data.

**Android phones** can also use **Bluetooth**: on the computer open **Bluetooth**
and follow the steps once.

## Weak Wi-Fi signal?

MyCursor is built for it. When the signal is weak the dot at the top of the
phone turns amber, and if the link drops you see **Weak signal. Reconnecting…**
for a few seconds while it comes back by itself — keep the app open; whatever
you typed meanwhile is sent as soon as it is back. Files you were sending carry
on from where they stopped.

If it stays weak, the best fix is the **Offline** page on the computer: the
phone then talks straight to the computer instead of through a far-away router,
so the signal is strong even where the Wi-Fi is not.

## If something does not work

- **The phone shows a white page:** it cannot reach the computer. Check that
  the computer is awake and MyCursor is running (it starts with Windows), and
  that both are on the same Wi-Fi. The phone app reconnects by itself as soon
  as it can.
- **The phone cannot open the link:** phone and computer must be on the same
  Wi-Fi. Guest or school Wi-Fi often blocks devices from seeing each other — use
  **Offline connection** instead.
- **"Windows Firewall may be blocking phones"** in the computer window: click
  **Allow phones to connect** and choose **Yes**.
- **Computer without a mouse** (for example a broken touchpad): Windows hides
  its pointer when it sees no mouse. MyCursor switches on Windows **Mouse Keys**
  while it runs so the real pointer shows, and switches it back when you quit.
  On keyboards with a number pad, with Num Lock off the number keys move the
  pointer while MyCursor runs.
- **Bluetooth says it did not start:** close other MyCursor windows, or turn
  Bluetooth off and on in Windows settings.
- **Need help?** Send the file `%LOCALAPPDATA%\MyCursor\mycursor.log`
  (paste that into the File Explorer address bar).

MyCursor only sends pointer and keyboard actions to your own computer. It never
sees your screen, and nothing goes to the internet.
