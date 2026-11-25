# Running News Forum on Another PC

How to set up a copied `News Forum` folder (for example on a home PC) so it starts in the background
at Windows login, the same way as on the laptop. It uses a Startup-folder shortcut that runs
`pythonw.exe -m news --no-browser` with no window. See also
[DEVELOPER-GUIDE.md](DEVELOPER-GUIDE.md#start-at-windows-login).

## Steps

**1. Install Python 3.13** from python.org, with the `py` launcher ticked, if it isn't installed
already.

**2. Install the dependencies.** Open PowerShell in the `News Forum` folder:

```powershell
py -3.13 -m pip install -r requirements.txt
```

**3. Check it runs.** Double-click `Start News Forum.bat`. The page at <http://127.0.0.1:8770>
should open. Close the window once it works.

**4. Create the Startup shortcut.** Run this from the same `News Forum` folder. It finds your
`pythonw.exe` itself, because its path differs from one PC to another:

```powershell
$pyw = (py -3.13 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))")
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\News Forum.lnk")
$lnk.TargetPath = $pyw
$lnk.Arguments = "-m news --no-browser"
$lnk.WorkingDirectory = (Get-Location).Path
$lnk.WindowStyle = 7
$lnk.Save()
"Shortcut -> $pyw"
```

Run it from inside the folder because the shortcut's "Start in" must be the `News Forum` folder.
That's how Python finds the `news` package.

**5. Start it now without logging out.** Press `Win+R`, type `shell:startup` and double-click
`News Forum`, or log out and back in. Then bookmark <http://127.0.0.1:8770>.

## Things to check

- **`.env`** holds the Telegram bot token and is git-ignored. A copied folder already has it. A
  clone from GitHub doesn't, so copy `.env` over by hand.
- **Two PCs, one bot:** if both PCs run with the same Telegram settings, the price messages arrive
  twice. Remove the Telegram settings from one PC's `.env` if you don't want that.
- **Troubleshooting:** there's no window, so check `data\news-forum.log` in the project folder.
- **Stop it:**
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | ? CommandLine -like '*-m news*' | % { Stop-Process -Id $_.ProcessId }
  ```
- **Turn off autostart:** delete `News Forum.lnk` from `shell:startup`.

## News sources by tab

All news comes from 25 free public RSS feeds listed in `feeds.json`. No API key is needed. The
`category` of each entry decides its tab.

| Tab (`category`) | Sources |
|---|---|
| World (`world`) | BBC World, Al Jazeera, DW, The Guardian, NPR, France 24 |
| Business (`business`) | BBC Business, CNBC, Guardian Business |
| Crypto & Investing (`markets`) | CoinDesk, Cointelegraph, Decrypt, CNBC Markets, CNBC Investing, Guardian Money |
| Asia (`asia`) | CNA (Channel NewsAsia), Nikkei Asia, Bangkok Post, The Diplomat, BBC Asia |
| AI (`tech`) | The Verge AI, The Decoder, MIT Tech Review AI, Guardian AI, Wired AI |

To add a source, add a line to `feeds.json` with a `name`, a `category` (one of `world`,
`business`, `markets`, `asia`, `tech`) and its RSS `url`, then restart the app.
