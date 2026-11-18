<#
agent-setup.ps1 -- set up a Kalmido project agent on Windows with one command (2.44.0, #1517).

Kalmido shows the command in Settings > Agents > (agent) > "Set up on a computer", e.g. (PowerShell):
  $env:KALMIDO_SETUP_CODE='ks_...'; & ([scriptblock]::Create((irm https://tasks.example.com/agent-setup.ps1))) -Url https://tasks.example.com -Dir "$HOME\projects\site"
It trades the one-time setup code for the agent's token (stored in a file only your Windows account can read, never
printed), fetches the starter files (mcp/starter_files.txt) and starts the agent in event mode at every login, hidden, with
the Task Scheduler (no admin rights; when the Task Scheduler refuses, a hidden entry in your Startup folder). One instance
per project folder. Needs: Windows PowerShell 5.1 or PowerShell 7, Python 3.9+, the agent command (default: claude).

  -Url          your Kalmido address
  -Code         the one-time setup code (15 minutes, works once; make a new one in Kalmido when it expired); better in the
                environment as KALMIDO_SETUP_CODE (not in the process list of the computer; removed from it once read)
  -Dir          the project folder the agent works in (created when missing)
  -Tool         2.391.0 (#3359): which tool runs the agent: claude (Claude Code, the default) or codex (Codex CLI); without
                -Tool and -Cmd the setup asks once (Enter = Claude Code; not interactive = Claude Code)
  -Cmd          the agent command (default: the tool's, claude / codex); Claude Code gets --mcp-config with the Kalmido MCP
                server, Codex CLI the same server with -c mcp_servers.kalmido.command=... (no change of config.toml)
  -From DIR     take the starter files from a local copy of mcp\ instead of downloading them
  -NoAutostart  install everything but the autostart
  -Lang         language of the messages: de, en, es, fr, it or nl (Kalmido adds the language of your account; anything else = en)
  -DryRun       only show what would happen: no code is redeemed, nothing is written, no task is registered
  -AllowHttp    2.360.0: an http:// address that is not this computer (localhost) -- only for a Kalmido without https
  -Template     2.1367.0 (#2700): the rules for the project folder: general (the Kalmido rules, the default) or software
                (+ the rules for building software and BRIEF-TEMPLATE.md; an existing CLAUDE.md stays, the rules come next to
                it as CLAUDE.software.md)
  -IpRule       2.1367.0 (#6457): an address rule for this computer's key: current (the address it reaches Kalmido from),
                off, or IPs / networks separated by commas; without it the setup asks once (Enter = no rule; not
                interactive = no rule)
  (2.360.0: without -Code the code comes from the environment variable KALMIDO_SETUP_CODE)
  -Uninstall    stop and remove the autostart, revoke this computer's token in Kalmido, delete the instance folder
Files: %LOCALAPPDATA%\Kalmido\agents\<folder name>-<hash>\ (starter files, kalmido-agent.env, mcp.json, agent.log);
2.1367.0 (#6457): Claude Code's deny rules in <folder>\.claude\settings.local.json.
#>
param([string]$Url = '', [string]$Code = '', [string]$Dir = '', [string]$Cmd = '', [string]$From = '',
      [switch]$NoAutostart, [switch]$DryRun, [switch]$Uninstall, [string]$Lang = 'en', [switch]$AllowHttp, [string]$Tool = '',
      [string]$IpRule = '', [string]$Template = 'general')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is slow with the progress bar in 5.1
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

# 2.46.6 (#1713): messages in German or English (-Lang); 2.574.0 (#3759): also es, fr, it, nl; anything else = English. M 'key' args... formats with -f.
$script:LangCode = $Lang.ToLowerInvariant().Substring(0, [Math]::Min(2, $Lang.Length))
$MsgEn = @{
  wrongos = 'this script is for Windows; on macOS and Linux use agent-setup.sh (Kalmido shows that command when you pick Mac or Linux)'
  undone = 'undone (the token is revoked again)'
  s_prereq = 'Checking what is needed'
  py = '  - Python 3.9 or newer: winget install Python.Python.3.12  (then open a new PowerShell window)'
  claude = '  - Claude Code: irm https://claude.ai/install.ps1 | iex  and then  claude  once to log in'
  cmd = '  - the agent command {0}'
  codex = '  - Codex CLI: npm install -g @openai/codex  and then  codex login  once to log in'
  notlogged_codex = '  note: Codex CLI seems not logged in yet; run  codex login  once'
  ask_tool = 'Which tool should run the agent? 1 = Claude Code (default), 2 = Codex CLI'
  badtool = 'unknown tool {0} (-Tool claude or codex)'
  missing = 'missing on this computer:\n{0}\nInstall it and run the same command again (make a new code in Kalmido if 15 minutes have passed).'
  agentcmd = '  agent command: {0}'
  notlogged = '  note: Claude Code seems not logged in yet; run  claude  once and log in'
  nodir = '-Dir FOLDER is missing (the project folder the agent works in)'
  folder = '  project folder: {0}'
  instance = '  instance: {0}'
  rev_ok = '  this computer is removed in Kalmido (its token no longer works)'
  rev_gone = '  the key of this computer was already revoked in Kalmido (agent deleted or computer removed): cleaning up here only'
  rev_fail = '  Kalmido did not answer: remove the computer in Settings > Agents if it is still listed'
  dry_stop = '  (dry run) stop and remove the task ''{0}'' and {1}'
  s_uninstall = 'Removing the agent of {0} from this computer'
  dry_revoke = '  (dry run) revoke this computer''s token in Kalmido and delete {0}'
  uninstalled = 'Done. The project folder itself stays as it is.'
  nourl = '-Url is missing (your Kalmido address)'
  nocode = '-Code is missing (the one-time code from Kalmido)'
  s_connect = 'Connecting to Kalmido'
  dry_redeem = '  (dry run) trade the code for the agent''s token at {0}/api/agent-setup/redeem (computer {1})'
  refused = 'Kalmido refused the code or is not reachable: {0} (nothing was installed)'
  agent = '  agent: {0}, token stored in {1} (only readable for you)'
  perm_you = '  permission questions are answered by account id {0} (who made the code); change it: in Kalmido, the agent''s Runtime > Permission questions go to (or KALMIDO_PERM_USER in {1})'
  perm_kept = '  permission questions: as set before (KALMIDO_PERM_USER / KALMIDO_OWNER_IDS in {0})'
  perm_none = '  permission questions: nobody set, every one is denied; choose a person in Kalmido (the agent''s Runtime > Permission questions go to) or add KALMIDO_PERM_USER=<account id> to {0}'
  perm_owner = '  permission questions are answered by the agent''s owner'
  claude_new = '  CLAUDE.md created: {0} (from the template; add your own rules on top)'
  claude_kept = '  CLAUDE.md exists, left as it is: {0}'
  dry_claude = '  (dry run) create CLAUDE.md from the template when there is none: {0}'
  badtpl = 'unknown template {0} (-Template general or software)'
  tpl_claude = '  Rules of the template Software development added to CLAUDE.md'
  tpl_prop = '  CLAUDE.md stays as it is; the rules of the template Software development are next to it as a proposal: {0}'
  tpl_propkept = '  The template''s proposal exists, left as it is: {0}'
  tpl_brief = '  Brief template created: {0}'
  tpl_briefkept = '  Brief template exists, left as it is: {0}'
  dry_tpl = '  (dry run) template Software development: rules in CLAUDE.md (or as a proposal next to it) and the brief template {0}'
  ask_ip = 'Should this computer''s key work only from its current internet address? Recommended for a fixed address; if it changes, the agent cannot reach Kalmido until you change the rule in Kalmido. [y/N]'
  ip_set = '  The key works only from: {0}'
  ip_wide = '  Address rule not set: the agent already has its own, narrower rule ({0})'
  harden = '  Deny rules for Claude Code written: {0} (no WebFetch / WebSearch, no reading of the key file)'
  dry_harden = '  (dry run) write deny rules for Claude Code into: {0}'
  harden_fail = '  The deny rules could not be written ({0} is not valid JSON); add them by hand, see the guide'
  badip = '-IpRule: current, off or addresses / networks separated by commas (e.g. 203.0.113.7,2001:db8::/64)'
  s_starter = 'Fetching the starter files'
  dry_files = '  (dry run) the files of {0}/starter_files.txt into {1}'
  nobase = 'Kalmido sent no address for the starter files; use -From DIR'
  nohttp = '{0} is an http:// address: the code and the token would cross the network unencrypted. Use the https:// address (or -AllowHttp when your Kalmido has no https)'
  basehttp = 'Kalmido sent an address without https:// for the starter files ({0}); use -From DIR'
  nolist = 'no starter_files.txt in {0}'
  nolistfetch = 'cannot fetch the starter file list ({0}starter_files.txt); this version may not be published yet - try again later or use -From DIR'
  skippath = '  skipped {0} (no paths allowed)'
  nofetch = 'cannot fetch {0}'
  shabad = '{0} does not match the checksum Kalmido sent - not installed. The download address serves another file than this version; ask your Kalmido admin'
  shanone = '  (Kalmido sent no checksums of the starter files: an older version, not checked)'
  skipfile = '  {0} not available (skipped)'
  dry_mcp = '  (dry run) write {0} (MCP server kalmido: {1} {2})'
  s_auto = 'Starting it at every login'
  noauto = '  skipped (-NoAutostart); start it with:'
  dry_task = '  (dry run) task ''\Kalmido\{0}'' at logon of {1}, hidden: {2} {3}'
  taskok = '  task ''\Kalmido\{0}'' (starts at login, hidden, restarts after a crash; log: {1}, the event runner writes agent_run.log next to it)'
  taskfail = '  the Task Scheduler refused ({0}); using your Startup folder instead'
  startupok = '  Startup folder entry {0} (starts at login; log: {1})'
  s_done = 'Done'
  done1 = 'Kalmido shows the computer under Settings > Agents within a minute (green dot = connected).'
  done2 = 'Remove it again:  & ([scriptblock]::Create((irm {0}/agent-setup.ps1))) -Uninstall -Dir {1}'
}
$MsgDe = @{
  wrongos = 'dieses Skript ist für Windows; unter macOS und Linux nimm agent-setup.sh (Kalmido zeigt den Befehl, wenn du Mac oder Linux wählst)'
  undone = 'rückgängig gemacht (das Token ist wieder gesperrt)'
  s_prereq = 'Prüfe, was gebraucht wird'
  py = '  - Python 3.9 oder neuer: winget install Python.Python.3.12  (danach ein neues PowerShell-Fenster öffnen)'
  claude = '  - Claude Code: irm https://claude.ai/install.ps1 | iex  und danach einmal  claude  zum Anmelden'
  cmd = '  - der Agent-Befehl {0}'
  codex = '  - Codex CLI: npm install -g @openai/codex  und danach einmal  codex login  zum Anmelden'
  notlogged_codex = '  Hinweis: Codex CLI scheint noch nicht angemeldet zu sein; führe  codex login  einmal aus'
  ask_tool = 'Welches Werkzeug soll den Agenten ausführen? 1 = Claude Code (Vorgabe), 2 = Codex CLI'
  badtool = 'unbekanntes Werkzeug {0} (-Tool claude oder codex)'
  missing = 'auf diesem Computer fehlt noch:\n{0}\nInstalliere es und führe denselben Befehl noch einmal aus (erzeuge in Kalmido einen neuen Code, wenn 15 Minuten vorbei sind).'
  agentcmd = '  Agent-Befehl: {0}'
  notlogged = '  Hinweis: Claude Code scheint noch nicht angemeldet zu sein; führe  claude  einmal aus und melde dich an'
  nodir = '-Dir ORDNER fehlt (der Projektordner, in dem der Agent arbeitet)'
  folder = '  Projektordner: {0}'
  instance = '  Instanz: {0}'
  rev_ok = '  dieser Computer ist in Kalmido entfernt (sein Token funktioniert nicht mehr)'
  rev_gone = '  der Schlüssel dieses Computers war in Kalmido schon widerrufen (Agent gelöscht oder Computer entfernt): es wird nur hier aufgeräumt'
  rev_fail = '  Kalmido hat nicht geantwortet: entferne den Computer unter Einstellungen > Agenten, falls er noch aufgelistet ist'
  dry_stop = '  (Probelauf) die Aufgabe ''{0}'' und {1} stoppen und entfernen'
  s_uninstall = 'Entferne den Agenten von {0} von diesem Computer'
  dry_revoke = '  (Probelauf) das Token dieses Computers in Kalmido sperren und {0} löschen'
  uninstalled = 'Fertig. Der Projektordner selbst bleibt unverändert.'
  nourl = '-Url fehlt (deine Kalmido-Adresse)'
  nocode = '-Code fehlt (der einmalige Code aus Kalmido)'
  s_connect = 'Verbinde mit Kalmido'
  dry_redeem = '  (Probelauf) den Code gegen das Token des Agenten tauschen unter {0}/api/agent-setup/redeem (Computer {1})'
  refused = 'Kalmido hat den Code abgelehnt oder ist nicht erreichbar: {0} (es wurde nichts installiert)'
  agent = '  Agent: {0}, Token gespeichert in {1} (nur für dich lesbar)'
  perm_you = '  Rechte-Fragen beantwortet Konto-Id {0} (wer den Code erzeugt hat); ändern: in Kalmido beim Agenten unter Laufzeit > Rechte-Fragen an (oder KALMIDO_PERM_USER in {1})'
  perm_kept = '  Rechte-Fragen: wie bisher eingestellt (KALMIDO_PERM_USER / KALMIDO_OWNER_IDS in {0})'
  perm_none = '  Rechte-Fragen: niemand eingetragen, jede wird abgelehnt; wähle in Kalmido beim Agenten unter Laufzeit > Rechte-Fragen an eine Person oder trage KALMIDO_PERM_USER=<Konto-Id> in {0} ein'
  perm_owner = '  Rechte-Fragen beantwortet die Person, der der Agent gehört'
  claude_new = '  CLAUDE.md angelegt: {0} (aus der Vorlage; eigene Regeln oben ergänzen)'
  claude_kept = '  CLAUDE.md vorhanden, bleibt unverändert: {0}'
  dry_claude = '  (Probelauf) CLAUDE.md aus der Vorlage anlegen, wenn keine da ist: {0}'
  badtpl = 'unbekannte Vorlage {0} (-Template general oder software)'
  tpl_claude = '  Regeln der Vorlage Software-Entwicklung in CLAUDE.md aufgenommen'
  tpl_prop = '  CLAUDE.md bleibt unverändert; die Regeln der Vorlage Software-Entwicklung liegen als Vorschlag daneben: {0}'
  tpl_propkept = '  Vorschlag der Vorlage vorhanden, bleibt unverändert: {0}'
  tpl_brief = '  Brief-Vorlage angelegt: {0}'
  tpl_briefkept = '  Brief-Vorlage vorhanden, bleibt unverändert: {0}'
  dry_tpl = '  (Probelauf) Vorlage Software-Entwicklung: Regeln in CLAUDE.md (oder als Vorschlag daneben) und Brief-Vorlage {0}'
  ask_ip = 'Soll der Schlüssel dieses Computers nur von seiner jetzigen Internet-Adresse aus gelten? Empfohlen bei fester Adresse; wechselt sie, erreicht der Agent Kalmido nicht mehr, bis du die Regel in Kalmido änderst. [j/N]'
  ip_set = '  Schlüssel gilt nur von: {0}'
  ip_wide = '  Adress-Regel nicht gesetzt: der Agent hat schon eine eigene, engere Regel ({0})'
  harden = '  Sperrregeln für Claude Code eingetragen: {0} (kein WebFetch / WebSearch, kein Lesen der Schlüssel-Datei)'
  dry_harden = '  (Probelauf) Sperrregeln für Claude Code eintragen in: {0}'
  harden_fail = '  Sperrregeln konnten nicht eingetragen werden ({0} ist kein gültiges JSON); trag sie von Hand ein, siehe Anleitung'
  badip = '-IpRule: current, off oder Adressen/Netze mit Komma (z. B. 203.0.113.7,2001:db8::/64)'
  s_starter = 'Lade die Starter-Dateien'
  dry_files = '  (Probelauf) die Dateien aus {0}/starter_files.txt nach {1}'
  nobase = 'Kalmido hat keine Adresse für die Starter-Dateien geschickt; nimm -From ORDNER'
  nohttp = '{0} ist eine http://-Adresse: der Code und das Token gingen unverschlüsselt durchs Netz. Nimm die https://-Adresse (oder -AllowHttp, wenn dein Kalmido kein https hat)'
  basehttp = 'Kalmido hat für die Starter-Dateien eine Adresse ohne https:// geschickt ({0}); nimm -From ORDNER'
  nolist = 'keine starter_files.txt in {0}'
  nolistfetch = 'die Liste der Starter-Dateien ({0}starter_files.txt) kann nicht geladen werden; diese Version ist vielleicht noch nicht veröffentlicht – versuche es später noch einmal oder nimm -From ORDNER'
  skippath = '  {0} übersprungen (keine Pfade erlaubt)'
  nofetch = '{0} kann nicht geladen werden'
  shabad = '{0} weicht von der Prüfsumme ab, die Kalmido geschickt hat – nicht installiert. Die Download-Adresse liefert eine andere Datei als diese Version; frag deinen Kalmido-Admin'
  shanone = '  (Kalmido hat keine Prüfsummen der Starter-Dateien geschickt: ältere Version, nicht geprüft)'
  skipfile = '  {0} nicht verfügbar (übersprungen)'
  dry_mcp = '  (Probelauf) {0} schreiben (MCP-Server kalmido: {1} {2})'
  s_auto = 'Starte bei jeder Anmeldung'
  noauto = '  übersprungen (-NoAutostart); starte es mit:'
  dry_task = '  (Probelauf) Aufgabe ''\Kalmido\{0}'' bei der Anmeldung von {1}, unsichtbar: {2} {3}'
  taskok = '  Aufgabe ''\Kalmido\{0}'' (startet bei der Anmeldung, unsichtbar, startet nach einem Absturz neu; Protokoll: {1}, der Ereignis-Runner schreibt zusätzlich agent_run.log daneben)'
  taskfail = '  die Aufgabenplanung hat abgelehnt ({0}); nehme stattdessen deinen Autostart-Ordner'
  startupok = '  Eintrag im Autostart-Ordner {0} (startet bei der Anmeldung; Protokoll: {1})'
  s_done = 'Fertig'
  done1 = 'Kalmido zeigt den Computer innerhalb einer Minute unter Einstellungen > Agenten (grüner Punkt = verbunden).'
  done2 = 'Wieder entfernen:  & ([scriptblock]::Create((irm {0}/agent-setup.ps1))) -Uninstall -Dir {1}'
}
$MsgEs = @{
  wrongos = 'este script es para Windows; en macOS y Linux usa agent-setup.sh (Kalmido muestra ese comando cuando eliges Mac o Linux)'
  undone = 'deshecho (el token vuelve a estar revocado)'
  s_prereq = 'Comprobando lo que hace falta'
  py = '  - Python 3.9 o más reciente: winget install Python.Python.3.12  (después abre una ventana nueva de PowerShell)'
  claude = '  - Claude Code: irm https://claude.ai/install.ps1 | iex  y después  claude  una vez para iniciar sesión'
  cmd = '  - el comando del agente {0}'
  codex = '  - Codex CLI: npm install -g @openai/codex  y después  codex login  una vez para iniciar sesión'
  notlogged_codex = '  nota: Codex CLI parece no haber iniciado sesión todavía; ejecuta  codex login  una vez'
  ask_tool = '¿Qué herramienta debe ejecutar el agente? 1 = Claude Code (predeterminada), 2 = Codex CLI'
  badtool = 'herramienta desconocida {0} (-Tool claude o codex)'
  missing = 'falta en este ordenador:\n{0}\nInstálalo y ejecuta el mismo comando otra vez (crea un código nuevo en Kalmido si han pasado 15 minutos).'
  agentcmd = '  comando del agente: {0}'
  notlogged = '  nota: Claude Code parece no haber iniciado sesión todavía; ejecuta  claude  una vez e inicia sesión'
  nodir = 'falta -Dir CARPETA (la carpeta del proyecto en la que trabaja el agente)'
  folder = '  carpeta del proyecto: {0}'
  instance = '  instancia: {0}'
  rev_ok = '  este ordenador se ha quitado en Kalmido (su token ya no funciona)'
  rev_gone = '  la clave de este ordenador ya estaba revocada en Kalmido (agente eliminado u ordenador quitado): solo se limpia aquí'
  rev_fail = '  Kalmido no ha respondido: quita el ordenador en Ajustes > Agentes si todavía aparece en la lista'
  dry_stop = '  (simulacro) detener y quitar la tarea ''{0}'' y {1}'
  s_uninstall = 'Quitando de este ordenador el agente de {0}'
  dry_revoke = '  (simulacro) revocar en Kalmido el token de este ordenador y eliminar {0}'
  uninstalled = 'Listo. La carpeta del proyecto se queda tal como está.'
  nourl = 'falta -Url (tu dirección de Kalmido)'
  nocode = 'falta -Code (el código de un solo uso de Kalmido)'
  s_connect = 'Conectando con Kalmido'
  dry_redeem = '  (simulacro) canjear el código por el token del agente en {0}/api/agent-setup/redeem (ordenador {1})'
  refused = 'Kalmido ha rechazado el código o no está accesible: {0} (no se instaló nada)'
  agent = '  agente: {0}, token guardado en {1} (solo legible para ti)'
  perm_you = '  las preguntas de permiso las responde la cuenta con id {0} (quien creó el código); cambiarlo: en Kalmido, en el agente, Ejecución > Preguntas de permiso a (o KALMIDO_PERM_USER en {1})'
  perm_kept = '  preguntas de permiso: como estaban configuradas (KALMIDO_PERM_USER / KALMIDO_OWNER_IDS en {0})'
  perm_none = '  preguntas de permiso: no hay nadie asignado, todas se deniegan; elige una persona en Kalmido (en el agente, Ejecución > Preguntas de permiso a) o añade KALMIDO_PERM_USER=<id de cuenta> a {0}'
  perm_owner = '  las preguntas de permiso las responde la persona a la que pertenece el agente'
  claude_new = '  CLAUDE.md creado: {0} (a partir de la plantilla; añade tus propias reglas arriba)'
  claude_kept = '  CLAUDE.md ya existe, se deja como está: {0}'
  dry_claude = '  (simulacro) crear CLAUDE.md a partir de la plantilla si no hay ninguno: {0}'
  badtpl = 'plantilla desconocida {0} (-Template general o software)'
  tpl_claude = '  Reglas de la plantilla Desarrollo de software añadidas a CLAUDE.md'
  tpl_prop = '  CLAUDE.md se deja como está; las reglas de la plantilla Desarrollo de software están al lado como propuesta: {0}'
  tpl_propkept = '  La propuesta de la plantilla ya existe, se deja como está: {0}'
  tpl_brief = '  Plantilla de brief creada: {0}'
  tpl_briefkept = '  La plantilla de brief ya existe, se deja como está: {0}'
  dry_tpl = '  (simulacro) plantilla Desarrollo de software: reglas en CLAUDE.md (o como propuesta al lado) y la plantilla de brief {0}'
  ask_ip = '¿La clave de este ordenador debe funcionar solo desde su dirección de internet actual? Recomendado con dirección fija; si cambia, el agente no llega a Kalmido hasta que cambies la regla en Kalmido. [s/N]'
  ip_set = '  La clave solo funciona desde: {0}'
  ip_wide = '  Regla de direcciones no puesta: el agente ya tiene una propia más estrecha ({0})'
  harden = '  Reglas de bloqueo para Claude Code escritas: {0} (sin WebFetch / WebSearch, sin leer el archivo de la clave)'
  dry_harden = '  (simulacro) escribir reglas de bloqueo para Claude Code en: {0}'
  harden_fail = '  No se pudieron escribir las reglas de bloqueo ({0} no es JSON válido); añádelas a mano, ver la guía'
  badip = '-IpRule: current, off o direcciones / redes separadas por comas (p. ej. 203.0.113.7,2001:db8::/64)'
  s_starter = 'Descargando los archivos de inicio'
  dry_files = '  (simulacro) los archivos de {0}/starter_files.txt en {1}'
  nobase = 'Kalmido no ha enviado ninguna dirección para los archivos de inicio; usa -From CARPETA'
  nohttp = '{0} es una dirección http://: el código y el token viajarían sin cifrar por la red. Usa la dirección https:// (o -AllowHttp si tu Kalmido no tiene https)'
  basehttp = 'Kalmido ha enviado una dirección sin https:// para los archivos de inicio ({0}); usa -From CARPETA'
  nolist = 'no hay starter_files.txt en {0}'
  nolistfetch = 'no se puede descargar la lista de archivos de inicio ({0}starter_files.txt); puede que esta versión aún no esté publicada - inténtalo más tarde o usa -From CARPETA'
  skippath = '  {0} omitido (no se permiten rutas)'
  nofetch = 'no se puede descargar {0}'
  shabad = '{0} no coincide con la suma de verificación que envió Kalmido - no se ha instalado. La dirección de descarga sirve otro archivo distinto al de esta versión; consulta a tu administrador de Kalmido'
  shanone = '  (Kalmido no ha enviado sumas de verificación de los archivos de inicio: versión anterior, sin comprobar)'
  skipfile = '  {0} no disponible (omitido)'
  dry_mcp = '  (simulacro) escribir {0} (servidor MCP kalmido: {1} {2})'
  s_auto = 'Iniciándolo en cada inicio de sesión'
  noauto = '  omitido (-NoAutostart); inícialo con:'
  dry_task = '  (simulacro) tarea ''\Kalmido\{0}'' al iniciar sesión {1}, oculta: {2} {3}'
  taskok = '  tarea ''\Kalmido\{0}'' (arranca al iniciar sesión, oculta, se reinicia tras un fallo; registro: {1}, el ejecutor de eventos escribe además agent_run.log junto a él)'
  taskfail = '  el Programador de tareas lo ha rechazado ({0}); se usa en su lugar tu carpeta de Inicio'
  startupok = '  entrada en la carpeta de Inicio {0} (arranca al iniciar sesión; registro: {1})'
  s_done = 'Listo'
  done1 = 'Kalmido muestra el ordenador en Ajustes > Agentes en un minuto (punto verde = conectado).'
  done2 = 'Para quitarlo de nuevo:  & ([scriptblock]::Create((irm {0}/agent-setup.ps1))) -Uninstall -Dir {1}'
}
$MsgFr = @{
  wrongos = 'ce script est pour Windows ; sous macOS et Linux, utilise agent-setup.sh (Kalmido affiche cette commande quand tu choisis Mac ou Linux)'
  undone = 'annulé (le jeton est de nouveau révoqué)'
  s_prereq = 'Vérification de ce qui est nécessaire'
  py = '  - Python 3.9 ou plus récent : winget install Python.Python.3.12  (puis ouvre une nouvelle fenêtre PowerShell)'
  claude = '  - Claude Code : irm https://claude.ai/install.ps1 | iex  puis  claude  une fois pour te connecter'
  cmd = '  - la commande de l''agent {0}'
  codex = '  - Codex CLI : npm install -g @openai/codex  puis  codex login  une fois pour te connecter'
  notlogged_codex = '  remarque : Codex CLI ne semble pas encore connecté ; lance  codex login  une fois'
  ask_tool = 'Quel outil doit exécuter l''agent ? 1 = Claude Code (par défaut), 2 = Codex CLI'
  badtool = 'outil inconnu {0} (-Tool claude ou codex)'
  missing = 'il manque sur cet ordinateur :\n{0}\nInstalle-le et relance la même commande (crée un nouveau code dans Kalmido si 15 minutes se sont écoulées).'
  agentcmd = '  commande de l''agent : {0}'
  notlogged = '  remarque : Claude Code ne semble pas encore connecté ; lance  claude  une fois et connecte-toi'
  nodir = '-Dir DOSSIER manque (le dossier du projet dans lequel l''agent travaille)'
  folder = '  dossier du projet : {0}'
  instance = '  instance : {0}'
  rev_ok = '  cet ordinateur est retiré dans Kalmido (son jeton ne fonctionne plus)'
  rev_gone = '  la clé de cet ordinateur était déjà révoquée dans Kalmido (agent supprimé ou ordinateur retiré) : seul le nettoyage local est fait'
  rev_fail = '  Kalmido n''a pas répondu : retire l''ordinateur sous Paramètres > Agents s''il figure encore dans la liste'
  dry_stop = '  (essai à blanc) arrêter et supprimer la tâche ''{0}'' et {1}'
  s_uninstall = 'Suppression de l''agent de {0} sur cet ordinateur'
  dry_revoke = '  (essai à blanc) révoquer dans Kalmido le jeton de cet ordinateur et supprimer {0}'
  uninstalled = 'Terminé. Le dossier du projet reste tel quel.'
  nourl = '-Url manque (ton adresse Kalmido)'
  nocode = '-Code manque (le code à usage unique de Kalmido)'
  s_connect = 'Connexion à Kalmido'
  dry_redeem = '  (essai à blanc) échanger le code contre le jeton de l''agent sur {0}/api/agent-setup/redeem (ordinateur {1})'
  refused = 'Kalmido a refusé le code ou est inaccessible : {0} (rien n''a été installé)'
  agent = '  agent : {0}, jeton enregistré dans {1} (lisible par toi seul)'
  perm_you = '  les questions d''autorisation reçoivent leur réponse du compte d''id {0} (celui qui a créé le code) ; pour changer : dans Kalmido, sur l''agent, Exécution > Questions d''autorisation à (ou KALMIDO_PERM_USER dans {1})'
  perm_kept = '  questions d''autorisation : comme réglées auparavant (KALMIDO_PERM_USER / KALMIDO_OWNER_IDS dans {0})'
  perm_none = '  questions d''autorisation : personne n''est défini, toutes sont refusées ; choisis une personne dans Kalmido (sur l''agent, Exécution > Questions d''autorisation à) ou ajoute KALMIDO_PERM_USER=<id du compte> à {0}'
  perm_owner = '  les questions d''autorisation reçoivent leur réponse de la personne à qui appartient l''agent'
  claude_new = '  CLAUDE.md créé : {0} (d''après le modèle ; ajoute tes propres règles en haut)'
  claude_kept = '  CLAUDE.md existe déjà, laissé tel quel : {0}'
  dry_claude = '  (essai à blanc) créer CLAUDE.md d''après le modèle s''il n''y en a pas : {0}'
  badtpl = 'modèle inconnu {0} (-Template general ou software)'
  tpl_claude = '  Règles du modèle Développement logiciel ajoutées à CLAUDE.md'
  tpl_prop = '  CLAUDE.md reste tel quel ; les règles du modèle Développement logiciel sont à côté comme proposition : {0}'
  tpl_propkept = '  La proposition du modèle existe déjà, laissée telle quelle : {0}'
  tpl_brief = '  Modèle de brief créé : {0}'
  tpl_briefkept = '  Le modèle de brief existe déjà, laissé tel quel : {0}'
  dry_tpl = '  (essai à blanc) modèle Développement logiciel : règles dans CLAUDE.md (ou comme proposition à côté) et le modèle de brief {0}'
  ask_ip = 'La clé de cet ordinateur doit-elle fonctionner seulement depuis son adresse internet actuelle ? Recommandé avec une adresse fixe ; si elle change, l''agent n''atteint plus Kalmido jusqu''à ce que tu changes la règle dans Kalmido. [o/N]'
  ip_set = '  La clé fonctionne seulement depuis : {0}'
  ip_wide = '  Règle d''adresse non posée : l''agent a déjà sa propre règle, plus étroite ({0})'
  harden = '  Règles de blocage pour Claude Code écrites : {0} (pas de WebFetch / WebSearch, pas de lecture du fichier de la clé)'
  dry_harden = '  (essai à blanc) écrire les règles de blocage pour Claude Code dans : {0}'
  harden_fail = '  Les règles de blocage n''ont pas pu être écrites ({0} n''est pas du JSON valide) ; ajoute-les à la main, voir le guide'
  badip = '-IpRule : current, off ou des adresses / réseaux séparés par des virgules (p. ex. 203.0.113.7,2001:db8::/64)'
  s_starter = 'Téléchargement des fichiers de démarrage'
  dry_files = '  (essai à blanc) les fichiers de {0}/starter_files.txt dans {1}'
  nobase = 'Kalmido n''a envoyé aucune adresse pour les fichiers de démarrage ; utilise -From DOSSIER'
  nohttp = '{0} est une adresse http:// : le code et le jeton circuleraient non chiffrés sur le réseau. Utilise l''adresse https:// (ou -AllowHttp si ton Kalmido n''a pas https)'
  basehttp = 'Kalmido a envoyé une adresse sans https:// pour les fichiers de démarrage ({0}) ; utilise -From DOSSIER'
  nolist = 'pas de starter_files.txt dans {0}'
  nolistfetch = 'impossible de télécharger la liste des fichiers de démarrage ({0}starter_files.txt) ; cette version n''est peut-être pas encore publiée - réessaie plus tard ou utilise -From DOSSIER'
  skippath = '  {0} ignoré (chemins interdits)'
  nofetch = 'impossible de télécharger {0}'
  shabad = '{0} ne correspond pas à la somme de contrôle envoyée par Kalmido - non installé. L''adresse de téléchargement fournit un autre fichier que celui de cette version ; demande à ton administrateur Kalmido'
  shanone = '  (Kalmido n''a pas envoyé de sommes de contrôle des fichiers de démarrage : version plus ancienne, non vérifié)'
  skipfile = '  {0} indisponible (ignoré)'
  dry_mcp = '  (essai à blanc) écrire {0} (serveur MCP kalmido : {1} {2})'
  s_auto = 'Démarrage à chaque connexion'
  noauto = '  ignoré (-NoAutostart) ; démarre-le avec :'
  dry_task = '  (essai à blanc) tâche ''\Kalmido\{0}'' à la connexion de {1}, masquée : {2} {3}'
  taskok = '  tâche ''\Kalmido\{0}'' (démarre à la connexion, masquée, redémarre après un plantage ; journal : {1}, l''exécuteur d''événements écrit en plus agent_run.log à côté)'
  taskfail = '  le Planificateur de tâches a refusé ({0}) ; utilisation de ton dossier Démarrage à la place'
  startupok = '  entrée dans le dossier Démarrage {0} (démarre à la connexion ; journal : {1})'
  s_done = 'Terminé'
  done1 = 'Kalmido affiche l''ordinateur sous Paramètres > Agents en une minute (point vert = connecté).'
  done2 = 'Pour le retirer :  & ([scriptblock]::Create((irm {0}/agent-setup.ps1))) -Uninstall -Dir {1}'
}
$MsgIt = @{
  wrongos = 'questo script è per Windows; su macOS e Linux usa agent-setup.sh (Kalmido mostra quel comando quando scegli Mac o Linux)'
  undone = 'annullato (il token è di nuovo revocato)'
  s_prereq = 'Controllo di ciò che serve'
  py = '  - Python 3.9 o più recente: winget install Python.Python.3.12  (poi apri una nuova finestra di PowerShell)'
  claude = '  - Claude Code: irm https://claude.ai/install.ps1 | iex  e poi  claude  una volta per accedere'
  cmd = '  - il comando dell''agente {0}'
  codex = '  - Codex CLI: npm install -g @openai/codex  e poi  codex login  una volta per accedere'
  notlogged_codex = '  nota: Codex CLI sembra non avere ancora effettuato l''accesso; esegui  codex login  una volta'
  ask_tool = 'Quale strumento deve eseguire l''agente? 1 = Claude Code (predefinito), 2 = Codex CLI'
  badtool = 'strumento sconosciuto {0} (-Tool claude o codex)'
  missing = 'manca su questo computer:\n{0}\nInstallalo ed esegui di nuovo lo stesso comando (crea un nuovo codice in Kalmido se sono passati 15 minuti).'
  agentcmd = '  comando dell''agente: {0}'
  notlogged = '  nota: Claude Code sembra non avere ancora effettuato l''accesso; esegui  claude  una volta e accedi'
  nodir = 'manca -Dir CARTELLA (la cartella del progetto in cui lavora l''agente)'
  folder = '  cartella del progetto: {0}'
  instance = '  istanza: {0}'
  rev_ok = '  questo computer è stato rimosso in Kalmido (il suo token non funziona più)'
  rev_gone = '  la chiave di questo computer era già revocata in Kalmido (agente eliminato o computer rimosso): si pulisce solo qui'
  rev_fail = '  Kalmido non ha risposto: rimuovi il computer in Impostazioni > Agenti se è ancora elencato'
  dry_stop = '  (prova) fermare e rimuovere l''attività ''{0}'' e {1}'
  s_uninstall = 'Rimozione dell''agente di {0} da questo computer'
  dry_revoke = '  (prova) revocare in Kalmido il token di questo computer ed eliminare {0}'
  uninstalled = 'Fatto. La cartella del progetto resta com''è.'
  nourl = 'manca -Url (il tuo indirizzo Kalmido)'
  nocode = 'manca -Code (il codice monouso di Kalmido)'
  s_connect = 'Connessione a Kalmido'
  dry_redeem = '  (prova) scambiare il codice con il token dell''agente su {0}/api/agent-setup/redeem (computer {1})'
  refused = 'Kalmido ha rifiutato il codice o non è raggiungibile: {0} (non è stato installato nulla)'
  agent = '  agente: {0}, token salvato in {1} (leggibile solo da te)'
  perm_you = '  alle richieste di autorizzazione risponde l''account con id {0} (chi ha creato il codice); per cambiarlo: in Kalmido, nell''agente, Runtime > Richieste di autorizzazione a (oppure KALMIDO_PERM_USER in {1})'
  perm_kept = '  richieste di autorizzazione: come impostate prima (KALMIDO_PERM_USER / KALMIDO_OWNER_IDS in {0})'
  perm_none = '  richieste di autorizzazione: nessuno impostato, ogni richiesta viene negata; scegli una persona in Kalmido (nell''agente, Runtime > Richieste di autorizzazione a) oppure aggiungi KALMIDO_PERM_USER=<id account> a {0}'
  perm_owner = '  alle richieste di autorizzazione risponde la persona a cui appartiene l''agente'
  claude_new = '  CLAUDE.md creato: {0} (dal modello; aggiungi le tue regole in alto)'
  claude_kept = '  CLAUDE.md esiste già, lasciato com''è: {0}'
  dry_claude = '  (prova) creare CLAUDE.md dal modello se non ce n''è uno: {0}'
  badtpl = 'modello sconosciuto {0} (-Template general o software)'
  tpl_claude = '  Regole del modello Sviluppo software aggiunte a CLAUDE.md'
  tpl_prop = '  CLAUDE.md resta com''è; le regole del modello Sviluppo software sono accanto come proposta: {0}'
  tpl_propkept = '  La proposta del modello esiste già, lasciata com''è: {0}'
  tpl_brief = '  Modello di brief creato: {0}'
  tpl_briefkept = '  Il modello di brief esiste già, lasciato com''è: {0}'
  dry_tpl = '  (prova) modello Sviluppo software: regole in CLAUDE.md (o come proposta accanto) e il modello di brief {0}'
  ask_ip = 'La chiave di questo computer deve funzionare solo dal suo indirizzo internet attuale? Consigliato con indirizzo fisso; se cambia, l''agente non raggiunge Kalmido finché non cambi la regola in Kalmido. [s/N]'
  ip_set = '  La chiave funziona solo da: {0}'
  ip_wide = '  Regola di indirizzo non impostata: l''agente ha già una regola propria più stretta ({0})'
  harden = '  Regole di blocco per Claude Code scritte: {0} (niente WebFetch / WebSearch, niente lettura del file della chiave)'
  dry_harden = '  (prova) scrivere le regole di blocco per Claude Code in: {0}'
  harden_fail = '  Impossibile scrivere le regole di blocco ({0} non è JSON valido); aggiungile a mano, vedi la guida'
  badip = '-IpRule: current, off o indirizzi / reti separati da virgole (es. 203.0.113.7,2001:db8::/64)'
  s_starter = 'Scaricamento dei file di avvio'
  dry_files = '  (prova) i file di {0}/starter_files.txt in {1}'
  nobase = 'Kalmido non ha inviato alcun indirizzo per i file di avvio; usa -From CARTELLA'
  nohttp = '{0} è un indirizzo http://: il codice e il token viaggerebbero in rete senza cifratura. Usa l''indirizzo https:// (oppure -AllowHttp se il tuo Kalmido non ha https)'
  basehttp = 'Kalmido ha inviato un indirizzo senza https:// per i file di avvio ({0}); usa -From CARTELLA'
  nolist = 'nessun starter_files.txt in {0}'
  nolistfetch = 'impossibile scaricare l''elenco dei file di avvio ({0}starter_files.txt); questa versione potrebbe non essere ancora pubblicata - riprova più tardi o usa -From CARTELLA'
  skippath = '  {0} saltato (percorsi non consentiti)'
  nofetch = 'impossibile scaricare {0}'
  shabad = '{0} non corrisponde al checksum inviato da Kalmido - non installato. L''indirizzo di download fornisce un file diverso da quello di questa versione; chiedi al tuo amministratore Kalmido'
  shanone = '  (Kalmido non ha inviato i checksum dei file di avvio: versione precedente, non verificato)'
  skipfile = '  {0} non disponibile (saltato)'
  dry_mcp = '  (prova) scrivere {0} (server MCP kalmido: {1} {2})'
  s_auto = 'Avvio a ogni accesso'
  noauto = '  saltato (-NoAutostart); avvialo con:'
  dry_task = '  (prova) attività ''\Kalmido\{0}'' all''accesso di {1}, nascosta: {2} {3}'
  taskok = '  attività ''\Kalmido\{0}'' (parte all''accesso, nascosta, riparte dopo un arresto anomalo; registro: {1}, l''esecutore degli eventi scrive inoltre agent_run.log accanto)'
  taskfail = '  l''Utilità di pianificazione ha rifiutato ({0}); si usa invece la tua cartella Esecuzione automatica'
  startupok = '  voce nella cartella Esecuzione automatica {0} (parte all''accesso; registro: {1})'
  s_done = 'Fatto'
  done1 = 'Kalmido mostra il computer in Impostazioni > Agenti entro un minuto (punto verde = connesso).'
  done2 = 'Per rimuoverlo di nuovo:  & ([scriptblock]::Create((irm {0}/agent-setup.ps1))) -Uninstall -Dir {1}'
}
$MsgNl = @{
  wrongos = 'dit script is voor Windows; gebruik op macOS en Linux agent-setup.sh (Kalmido toont die opdracht als je Mac of Linux kiest)'
  undone = 'ongedaan gemaakt (het token is weer ingetrokken)'
  s_prereq = 'Controleren wat er nodig is'
  py = '  - Python 3.9 of nieuwer: winget install Python.Python.3.12  (open daarna een nieuw PowerShell-venster)'
  claude = '  - Claude Code: irm https://claude.ai/install.ps1 | iex  en daarna één keer  claude  om in te loggen'
  cmd = '  - de agentopdracht {0}'
  codex = '  - Codex CLI: npm install -g @openai/codex  en daarna één keer  codex login  om in te loggen'
  notlogged_codex = '  let op: Codex CLI lijkt nog niet ingelogd te zijn; voer één keer  codex login  uit'
  ask_tool = 'Welk hulpmiddel moet de agent uitvoeren? 1 = Claude Code (standaard), 2 = Codex CLI'
  badtool = 'onbekend hulpmiddel {0} (-Tool claude of codex)'
  missing = 'ontbreekt op deze computer:\n{0}\nInstalleer het en voer dezelfde opdracht opnieuw uit (maak een nieuwe code in Kalmido als er 15 minuten voorbij zijn).'
  agentcmd = '  agentopdracht: {0}'
  notlogged = '  let op: Claude Code lijkt nog niet ingelogd te zijn; voer één keer  claude  uit en log in'
  nodir = '-Dir MAP ontbreekt (de projectmap waarin de agent werkt)'
  folder = '  projectmap: {0}'
  instance = '  instantie: {0}'
  rev_ok = '  deze computer is verwijderd in Kalmido (zijn token werkt niet meer)'
  rev_gone = '  de sleutel van deze computer was in Kalmido al ingetrokken (agent verwijderd of computer verwijderd): alleen hier wordt opgeruimd'
  rev_fail = '  Kalmido heeft niet geantwoord: verwijder de computer onder Instellingen > Agents als hij nog in de lijst staat'
  dry_stop = '  (proefrun) de taak ''{0}'' en {1} stoppen en verwijderen'
  s_uninstall = 'De agent van {0} van deze computer verwijderen'
  dry_revoke = '  (proefrun) het token van deze computer in Kalmido intrekken en {0} verwijderen'
  uninstalled = 'Klaar. De projectmap zelf blijft zoals hij is.'
  nourl = '-Url ontbreekt (je Kalmido-adres)'
  nocode = '-Code ontbreekt (de eenmalige code uit Kalmido)'
  s_connect = 'Verbinden met Kalmido'
  dry_redeem = '  (proefrun) de code inruilen voor het token van de agent bij {0}/api/agent-setup/redeem (computer {1})'
  refused = 'Kalmido heeft de code geweigerd of is niet bereikbaar: {0} (er is niets geïnstalleerd)'
  agent = '  agent: {0}, token opgeslagen in {1} (alleen voor jou leesbaar)'
  perm_you = '  toestemmingsvragen worden beantwoord door het account met id {0} (wie de code maakte); wijzigen: in Kalmido, bij de agent, Runtime > Toestemmingsvragen naar (of KALMIDO_PERM_USER in {1})'
  perm_kept = '  toestemmingsvragen: zoals eerder ingesteld (KALMIDO_PERM_USER / KALMIDO_OWNER_IDS in {0})'
  perm_none = '  toestemmingsvragen: niemand ingesteld, elke vraag wordt geweigerd; kies een persoon in Kalmido (bij de agent, Runtime > Toestemmingsvragen naar) of voeg KALMIDO_PERM_USER=<account-id> toe aan {0}'
  perm_owner = '  toestemmingsvragen worden beantwoord door de eigenaar van de agent'
  claude_new = '  CLAUDE.md aangemaakt: {0} (uit de sjabloon; voeg je eigen regels bovenaan toe)'
  claude_kept = '  CLAUDE.md bestaat al, blijft zoals het is: {0}'
  dry_claude = '  (proefrun) CLAUDE.md aanmaken uit de sjabloon als er geen is: {0}'
  badtpl = 'onbekende sjabloon {0} (-Template general of software)'
  tpl_claude = '  Regels van de sjabloon Softwareontwikkeling toegevoegd aan CLAUDE.md'
  tpl_prop = '  CLAUDE.md blijft zoals het is; de regels van de sjabloon Softwareontwikkeling staan ernaast als voorstel: {0}'
  tpl_propkept = '  Het voorstel van de sjabloon bestaat al, blijft zoals het is: {0}'
  tpl_brief = '  Brief-sjabloon aangemaakt: {0}'
  tpl_briefkept = '  Brief-sjabloon bestaat al, blijft zoals het is: {0}'
  dry_tpl = '  (proefrun) sjabloon Softwareontwikkeling: regels in CLAUDE.md (of als voorstel ernaast) en de brief-sjabloon {0}'
  ask_ip = 'Moet de sleutel van deze computer alleen werken vanaf zijn huidige internetadres? Aanbevolen bij een vast adres; verandert het, dan bereikt de agent Kalmido niet meer tot je de regel in Kalmido aanpast. [j/N]'
  ip_set = '  De sleutel werkt alleen vanaf: {0}'
  ip_wide = '  Adresregel niet gezet: de agent heeft al een eigen, nauwere regel ({0})'
  harden = '  Blokkeerregels voor Claude Code geschreven: {0} (geen WebFetch / WebSearch, geen lezen van het sleutelbestand)'
  dry_harden = '  (proefrun) blokkeerregels voor Claude Code schrijven in: {0}'
  harden_fail = '  De blokkeerregels konden niet worden geschreven ({0} is geen geldige JSON); voeg ze met de hand toe, zie de handleiding'
  badip = '-IpRule: current, off of adressen / netwerken gescheiden door komma''s (bijv. 203.0.113.7,2001:db8::/64)'
  s_starter = 'De startbestanden ophalen'
  dry_files = '  (proefrun) de bestanden uit {0}/starter_files.txt naar {1}'
  nobase = 'Kalmido heeft geen adres voor de startbestanden gestuurd; gebruik -From MAP'
  nohttp = '{0} is een http://-adres: de code en het token zouden onversleuteld over het netwerk gaan. Gebruik het https://-adres (of -AllowHttp als je Kalmido geen https heeft)'
  basehttp = 'Kalmido heeft een adres zonder https:// voor de startbestanden gestuurd ({0}); gebruik -From MAP'
  nolist = 'geen starter_files.txt in {0}'
  nolistfetch = 'de lijst met startbestanden ({0}starter_files.txt) kan niet worden opgehaald; deze versie is misschien nog niet gepubliceerd - probeer het later opnieuw of gebruik -From MAP'
  skippath = '  {0} overgeslagen (paden niet toegestaan)'
  nofetch = '{0} kan niet worden opgehaald'
  shabad = '{0} komt niet overeen met de controlesom die Kalmido stuurde - niet geïnstalleerd. Het downloadadres levert een ander bestand dan deze versie; vraag het aan je Kalmido-beheerder'
  shanone = '  (Kalmido stuurde geen controlesommen van de startbestanden: oudere versie, niet gecontroleerd)'
  skipfile = '  {0} niet beschikbaar (overgeslagen)'
  dry_mcp = '  (proefrun) {0} schrijven (MCP-server kalmido: {1} {2})'
  s_auto = 'Bij elke aanmelding starten'
  noauto = '  overgeslagen (-NoAutostart); start het met:'
  dry_task = '  (proefrun) taak ''\Kalmido\{0}'' bij het aanmelden van {1}, verborgen: {2} {3}'
  taskok = '  taak ''\Kalmido\{0}'' (start bij het aanmelden, verborgen, start opnieuw na een crash; log: {1}, de gebeurtenis-runner schrijft ernaast ook agent_run.log)'
  taskfail = '  de Taakplanner heeft geweigerd ({0}); in plaats daarvan wordt je map Opstarten gebruikt'
  startupok = '  item in de map Opstarten {0} (start bij het aanmelden; log: {1})'
  s_done = 'Klaar'
  done1 = 'Kalmido toont de computer binnen een minuut onder Instellingen > Agents (groene stip = verbonden).'
  done2 = 'Om het weer te verwijderen:  & ([scriptblock]::Create((irm {0}/agent-setup.ps1))) -Uninstall -Dir {1}'
}
# 2.574.0 (#3759): the table of the account language (de, es, fr, it, nl); anything else = English; a text missing there = the English one
$script:LangTab = $null
switch ($script:LangCode) { 'de' { $script:LangTab = $MsgDe } 'es' { $script:LangTab = $MsgEs } 'fr' { $script:LangTab = $MsgFr } 'it' { $script:LangTab = $MsgIt } 'nl' { $script:LangTab = $MsgNl } }
function M([string]$k, [object[]]$a = @()) { $tab = $script:LangTab; $t = if ($tab -and $tab.ContainsKey($k) -and $tab[$k]) { $tab[$k] } else { $MsgEn[$k] }; $t = $t.Replace('\n', "`n"); if ($a.Count) { $t -f $a } else { $t } }
function Say([string]$m) { Write-Host $m }
function Step([string]$m) { Write-Host ''; Write-Host "== $m" }
$script:Redeemed = $false
function Die([string]$m) {
  [Console]::Error.WriteLine("agent-setup: $m")
  if ($script:Redeemed) { Revoke; Remove-Item -LiteralPath $Inst -Recurse -Force -ErrorAction SilentlyContinue; [Console]::Error.WriteLine('agent-setup: ' + (M 'undone')) }
  exit 1
}
$OnWindows = ($env:OS -eq 'Windows_NT')
if (-not $OnWindows -and -not $DryRun) { Die (M 'wrongos') }

# one answer typed on the console, 120 s like setup.sh (read -t 120); no answer = '' (2.1367.0: shared by the questions below)
function Ask([string]$q) {
  $ans = ''
  try {
    Write-Host -NoNewline ($q + ' ')
    $end = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $end) {
      if (-not [Console]::KeyAvailable) { Start-Sleep -Milliseconds 100; continue }
      $k = [Console]::ReadKey($true)
      if ($k.Key -eq 'Enter') { break }
      if ($k.Key -eq 'Backspace') { if ($ans.Length) { $ans = $ans.Substring(0, $ans.Length - 1); Write-Host -NoNewline "`b `b" }; continue }
      $ans += $k.KeyChar; Write-Host -NoNewline $k.KeyChar
    }
    Write-Host ''
  } catch { $ans = '' }
  return $ans
}
# 2.391.0 (#3359): the tool (Claude Code by default), asked once when neither -Tool nor -Cmd names it and the console is
# interactive; a dry run, the uninstall or no console: Claude Code
if (-not $Tool -and $Cmd) { $Tool = if ([IO.Path]::GetFileNameWithoutExtension($Cmd).ToLower() -eq 'codex') { 'codex' } else { 'claude' } }
if (-not $Tool -and -not $DryRun -and -not $Uninstall -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
  # 2.575.0 (#3948): with a 120 s timeout like setup.sh (read -t 120); no answer = Claude Code
  $ans = Ask (M 'ask_tool')
  if ("$ans".Trim() -in @('2', 'codex', 'Codex', 'Codex CLI')) { $Tool = 'codex' }
}
# 2.1367.0 (#6457): the address rule of this computer's key (api_tokens.allowed_ips, set by Kalmido at the redeem); asked once
# like the tool (default no: a home connection often changes its address); not interactive: none
if (-not $IpRule -and -not $DryRun -and -not $Uninstall -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
  if ("$(Ask (M 'ask_ip'))".Trim() -match '^[jJyYsSoO]') { $IpRule = 'current' }
}
if ($Template -notin @('general', 'software')) { Die (M 'badtpl' @($Template)) }
$Template = $Template.ToLowerInvariant()
if ($IpRule -in @('off', 'none')) { $IpRule = '' }
if ($IpRule -and $IpRule -ne 'current' -and $IpRule -notmatch '^[0-9A-Fa-f.:/, ]+$') { Die (M 'badip') }
if (-not $Tool) { $Tool = 'claude' }
$Tool = $Tool.ToLowerInvariant()
if ($Tool -notin @('claude', 'codex')) { Die (M 'badtool' @($Tool)) }
if (-not $Cmd) { $Cmd = $Tool }

# kalmido-setup-step: prereq
Step (M 's_prereq')
$missing = @()
$Py = $null; $PyArgs = @()
# 2.443.0 (#2940): KALMIDO_PYTHON first and alone, as in setup.sh
foreach ($n in $(if ($env:KALMIDO_PYTHON) { @($env:KALMIDO_PYTHON) } else { @('py', 'python', 'python3') })) {  # python3 may be the Microsoft Store stub: the version check sorts it out
  $c = Get-Command $n -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $c) { continue }
  $pa = @(); if ($n -eq 'py') { $pa = @('-3') }
  try { & $c.Source @pa -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>$null; if ($LASTEXITCODE -eq 0) { $Py = $c.Source; $PyArgs = $pa; break } } catch { }
}
if (-not $Py) { $missing += (M 'py') }
$Agent = $null
if (-not $Uninstall) {
  $c = Get-Command $Cmd -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c) { $Agent = $c.Source }
  foreach ($p in @("$env:USERPROFILE\.local\bin\$Cmd.exe", "$env:USERPROFILE\.claude\local\$Cmd.exe")) { if (-not $Agent -and (Test-Path -LiteralPath $p)) { $Agent = $p } }
  if (-not $Agent) {
    if ($Cmd -eq 'claude') { $missing += (M 'claude') }
    elseif ($Cmd -eq 'codex') { $missing += (M 'codex') }
    else { $missing += (M 'cmd' @($Cmd)) }
  }
}
if ($missing.Count) {
  [Console]::Error.WriteLine('agent-setup: ' + (M 'missing' @($missing -join "`n")))
  if (-not $DryRun) { exit 1 }
}
if ($Agent) { Say (M 'agentcmd' @($Agent)) }
if ($Cmd -eq 'claude' -and $Agent -and -not (Test-Path -LiteralPath "$env:USERPROFILE\.claude")) { Say (M 'notlogged') }
if ($Tool -eq 'codex' -and $Agent) {
  $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } elseif ($env:USERPROFILE) { Join-Path $env:USERPROFILE '.codex' } else { Join-Path $HOME '.codex' }
  if (-not (Test-Path -LiteralPath (Join-Path $CodexHome 'auth.json'))) { Say (M 'notlogged_codex') }
}

# kalmido-setup-step: instance
if (-not $Dir) { Die (M 'nodir') }
$Dir = $Dir -replace '^(\$HOME|\$env:USERPROFILE|%USERPROFILE%)(?=$|[\\/])', '~'  # 2.44.0 (review): a typed $HOME is no literal folder name
if ($Dir -eq '~' -or $Dir.StartsWith('~\') -or $Dir.StartsWith('~/')) { $Dir = $HOME + $Dir.Substring(1) }
$Dir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Dir).TrimEnd('\', '/')  # relative to the PowerShell location (5.1: GetFullPath would use the process directory)
$leaf = ([IO.Path]::GetFileName($Dir) -replace '[^A-Za-z0-9_.-]', '-'); if ($leaf.Length -gt 40) { $leaf = $leaf.Substring(0, 40) }
$sha = [Security.Cryptography.SHA1]::Create()
$hash = (($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Dir.ToLowerInvariant())) | Select-Object -First 4 | ForEach-Object { $_.ToString('x2') }) -join '')
$Slug = "$leaf-$hash"
$LocalBase = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME '.kalmido' }
$Inst = Join-Path (Join-Path (Join-Path $LocalBase 'Kalmido') 'agents') $Slug
$TaskName = "Kalmido agent $Slug"
$StartupDir = if ($env:APPDATA) { Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup' } else { Join-Path $HOME 'Startup' }
$StartupCmd = Join-Path $StartupDir "kalmido-agent-$Slug.cmd"
$EnvF = Join-Path $Inst 'kalmido-agent.env'
Say (M 'folder' @($Dir))
Say (M 'instance' @($Inst))

# revoke: this computer's token is revoked in Kalmido (POST /api/agent-setup/remove with the token itself)
function Revoke {
  if (-not (Test-Path -LiteralPath $EnvF)) { return }
  $e = @{}
  foreach ($l in Get-Content -LiteralPath $EnvF) { if ($l -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $e[$Matches[1]] = $Matches[2] } }
  try {
    Invoke-RestMethod -Method Post -Uri ($e['KALMIDO_URL'].TrimEnd('/') + '/api/agent-setup/remove') -Body '{}' -ContentType 'application/json' `
      -Headers @{ Authorization = "Bearer $($e['KALMIDO_TOKEN'])"; 'X-Requested-With' = 'kalmido' } -TimeoutSec 20 | Out-Null
    Say (M 'rev_ok')
  } catch {
    $code = 0; try { $code = [int]$_.Exception.Response.StatusCode } catch { $code = 0 }
    if ($code -eq 401) { Say (M 'rev_gone') } else { Say (M 'rev_fail') }  # 2.47.3 (#1729): already revoked = only a hint, the cleanup goes on
  }
}

# kalmido-setup-step: autostart_stop
function Stop-Autostart {
  if ($DryRun) { Say (M 'dry_stop' @($TaskName, $StartupCmd)); return }
  if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
    $t = Get-ScheduledTask -TaskPath '\Kalmido\' -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) { Stop-ScheduledTask -InputObject $t -ErrorAction SilentlyContinue; Unregister-ScheduledTask -InputObject $t -Confirm:$false }
  }
  if (Test-Path -LiteralPath $StartupCmd) { Remove-Item -LiteralPath $StartupCmd -Force }
  # the launcher of an earlier setup of this folder (its command line names the instance folder)
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Inst) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

if ($Uninstall) {
  # kalmido-setup-step: uninstall
  Step (M 's_uninstall' @($Dir))
  Stop-Autostart
  if ($DryRun) { Say (M 'dry_revoke' @($Inst)) }
  else { Revoke; if (Test-Path -LiteralPath $Inst) { Remove-Item -LiteralPath $Inst -Recurse -Force } }
  Say (M 'uninstalled')
  exit 0
}

if (-not $Url) { Die (M 'nourl') }
if (-not $Code) { $Code = [string]$env:KALMIDO_SETUP_CODE }  # 2.360.0 C (#2496)
Remove-Item Env:KALMIDO_SETUP_CODE -ErrorAction SilentlyContinue  # 2.360.0 R (#2496): not left in the PowerShell session
if (-not $Code -and -not $DryRun) { Die (M 'nocode') }
$Url = $Url.TrimEnd('/')
# 2.360.0 C (#2496): https only, except this computer (localhost) or -AllowHttp for a Kalmido without https
if (-not $AllowHttp -and $Url -notmatch '^https://' -and $Url -notmatch '^http://(localhost|127\.0\.0\.1|\[::1\])([:/]|$)') { Die (M 'nohttp' @($Url)) }

# kalmido-setup-step: redeem
Step (M 's_connect')
$HostN = ([Environment]::MachineName -split '\.')[0]
$StarterBase = ''
$StarterSha = @{}  # 2.380 G (#3390): file name -> sha256 from the redeem answer (empty: an older Kalmido, nothing checked)
if ($DryRun) { Say (M 'dry_redeem' @($Url, $HostN)) }
else {
  New-Item -ItemType Directory -Force -Path $Inst | Out-Null
  # only this Windows account may read the instance folder (inheritance off, one rule for the current user)
  $acl = Get-Acl -LiteralPath $Inst
  $acl.SetAccessRuleProtection($true, $false)
  foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRule($rule) }
  $me = [Security.Principal.WindowsIdentity]::GetCurrent().User
  $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($me, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
  Set-Acl -LiteralPath $Inst -AclObject $acl
  $bd = @{ code = $Code.Trim(); host = $HostN; folder = $Dir; os = 'windows' }
  # 2.1367.0 (#6457): "current" or IPs / networks; Kalmido sets the key's address rule (never wider than the agent's own)
  if ($IpRule) { $bd.allowed_ips = if ($IpRule -eq 'current') { 'current' } else { @($IpRule -split '[\s,]+' | Where-Object { $_ }) } }
  $body = $bd | ConvertTo-Json -Compress
  try {
    $r = Invoke-RestMethod -Method Post -Uri "$Url/api/agent-setup/redeem" -Body $body -ContentType 'application/json' -Headers @{ 'X-Requested-With' = 'kalmido' } -TimeoutSec 30
  } catch {
    $msg = ''; try { $msg = ($_.ErrorDetails.Message | ConvertFrom-Json).error } catch { }
    Die (M 'refused' @($(if ($msg) { $msg } else { $_.Exception.Message })))
  }
  # 2.306.0 (#2927): the name goes into a comment line: no control characters
  $AgName = [string]$r.agent.name -replace '[\x00-\x1f\x7f]', ' '
  $AgUser = [string]$r.agent.username -replace '[\x00-\x1f\x7f]', ' '
  $lines = @("# Kalmido agent $AgName ($AgUser), set up by agent-setup.ps1 -- keep this file private",
             "KALMIDO_URL=$Url", "KALMIDO_TOKEN=$($r.token)", 'KALMIDO_EVENTS=1', '# KALMIDO_TOOLSETS=tickets,code,chat   # optional (2.391.0): only these MCP tool packages, chat is always on; default: all',
             "KALMIDO_STATE_DIR=`"$(Join-Path $Inst 'state')`"")  # one state folder per instance (cursor, approvals, lock); 2.443.0 (#2940): quoted, a " #" in a value starts a comment
  $lines += "KALMIDO_PROJECT_DIR=`"$Dir`""  # 2.619.0 (#2383): the project folder named here; looked-at images only from it
  if ($env:KALMIDO_PYTHON) { $lines += "KALMIDO_PYTHON=`"$env:KALMIDO_PYTHON`"" }  # 2.443.0 (#2940): the autostart runs without this shell's variables
  # 2.306.0 E (#2927): who answers permission questions -- kept from an earlier setup of this folder, else (team agent) the
  # person who made the code (operator_id), as KALMIDO_PERM_USER; KALMIDO_OWNER_IDS would also narrow who gives orders
  $keep = @()
  if (Test-Path -LiteralPath $EnvF) { $keep = @(Get-Content -LiteralPath $EnvF | Where-Object { $_ -match '^KALMIDO_(PERM_USER|OWNER_IDS)=' }) }
  $op = $r.operator_id
  if ($keep.Count) { $perm = 'kept' }
  elseif ($null -ne $op -and "$op" -match '^\d+$') { $perm = "$op"; $keep = @("KALMIDO_PERM_USER=$op") }
  elseif ($r.agent.team) { $perm = 'none' }
  else { $perm = 'owner' }
  [IO.File]::WriteAllLines("$EnvF.new", @($lines + $keep))  # 2.443.0 (#2940): written whole, then moved into place, as in setup.sh
  Move-Item -LiteralPath "$EnvF.new" -Destination $EnvF -Force
  # 2.306.0 (#2927): the server's version next to the starter files (the MCP server reports it; they have no VERSION file)
  if ([string]$r.version -match '^\d+(\.\d+){1,3}$') { [IO.File]::WriteAllText((Join-Path $Inst 'VERSION'), "$($r.version)`n") }
  $script:Redeemed = $true
  $StarterBase = [string]$r.starter_base
  if ($r.starter_sha256) {
    foreach ($p in $r.starter_sha256.PSObject.Properties) { if ([string]$p.Value -match '^[0-9a-f]{64}$') { $StarterSha[$p.Name] = [string]$p.Value } }
  }
  Say (M 'agent' @($AgName, $EnvF))
  switch ($perm) {
    'kept' { Say (M 'perm_kept' @($EnvF)) }
    'none' { Say (M 'perm_none' @($EnvF)) }
    'owner' { Say (M 'perm_owner') }
    default { Say (M 'perm_you' @($perm, $EnvF)) }
  }
  $got = (@($r.allowed_ips) | Where-Object { "$_" -match '^[0-9A-Fa-f.:/]{2,50}$' }) -join ','  # 2.1367.0 (#6457)
  if ($IpRule -and $got) { if ($r.allowed_ips_applied) { Say (M 'ip_set' @($got)) } else { Say (M 'ip_wide' @($got)) } }
}

# kalmido-setup-step: starter_files
Step (M 's_starter')
$Required = @('agent_launcher.ps1', 'agent_run.py', 'kalmido_mcp.py')
function Fetch([string]$name, [string]$dest) {
  if ($From) { $src = Join-Path $From $name; if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination $dest -Force; return $true }; return $false }
  try { Invoke-WebRequest -Uri ($StarterBase + $name) -OutFile $dest -UseBasicParsing -TimeoutSec 60; return $true } catch { return $false }
}
# 2.380 G (#3390): a downloaded starter file must have the checksum Kalmido sent with the token; a file that differs or is not
# in the list stops the setup before it is installed. -From DIR (a local copy) and an older Kalmido without checksums: no check
function ShaOk([string]$name, [string]$file) {
  if ($From -or $StarterSha.Count -eq 0) { return $true }
  if (-not $StarterSha.ContainsKey($name)) { return $false }
  return (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower() -eq $StarterSha[$name]
}
function InstallStarter([string]$name, [string]$dest) {  # fetch into dest.new, check, then move into place -> $true when installed
  $tmp = "$dest.new"
  if (-not (Fetch $name $tmp)) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue; return $false }
  if (-not (ShaOk $name $tmp)) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue; Die (M 'shabad' @($name)) }
  Move-Item -LiteralPath $tmp -Destination $dest -Force
  return $true
}
if ($DryRun) { Say (M 'dry_files' @($(if ($From) { $From } else { 'starter' }), $Inst)) }
else {
  if (-not $From -and -not $StarterBase) { Die (M 'nobase') }
  # 2.360.0 C (#2496): the starter files (they run here) only over https or from this Kalmido itself
  if (-not $From -and $StarterBase -notmatch '^https://' -and -not $StarterBase.StartsWith($Url + '/')) { Die (M 'basehttp' @($StarterBase)) }
  if (-not $From -and $StarterSha.Count -eq 0) { Say (M 'shanone') }
  Get-ChildItem -LiteralPath $Inst -Filter '*.new' | Remove-Item -Force  # 2.443.0 (#2940): what a broken earlier setup left, as in setup.sh
  $list = Join-Path $Inst 'starter_files.txt'
  if (-not (InstallStarter 'starter_files.txt' $list)) {
    if ($From) { Die (M 'nolist' @($From)) }
    # 2.44.0 (review): no fallback to another branch -- the starter must match this instance's version
    Die (M 'nolistfetch' @($StarterBase))
  }
  foreach ($raw in Get-Content -LiteralPath $list) {
    $f = ($raw -replace '#.*$', '').Trim()
    if (-not $f) { continue }
    if ($f.Contains('/') -or $f.Contains('\') -or $f.StartsWith('..')) { Say (M 'skippath' @($f)); continue }
    if (InstallStarter $f (Join-Path $Inst $f)) { Say "  $f" }
    elseif ($Required -contains $f) { Die (M 'nofetch' @($f)) }
    else { Say (M 'skipfile' @($f)) }
  }
}

# kalmido-setup-step: mcp_config
# the agent command gets the MCP server with --mcp-config (works headless without a trust prompt); the token is in no config
# file but the env file (2.1367.0, #6457: the server reads it there, the launcher hands the model's process only its path)
$McpJ = Join-Path $Inst 'mcp.json'
$pyArgsJ = @($PyArgs + @((Join-Path $Inst 'kalmido_mcp.py')))
function Q([string]$s) { "'" + $s.Replace("'", "''") + "'" }
$McpArgs = "--mcp-config $(Q $McpJ)"
if ($Tool -eq 'codex') {
  # 2.391.0 (#3359): Codex CLI takes the same server per run (-c, nothing written into config.toml); Codex hands MCP servers
  # only a few environment variables, so a small wrapper next to the env file reads it and starts the server
  $McpJ = Join-Path $Inst 'kalmido_mcp_run.ps1'
  $PsHost = (Get-Process -Id $PID).Path -replace '\\', '/'
  # 2.575.0 (#3948): TOML basic strings (an apostrophe in the path, e.g. a user name like O'Neil, would end a literal string);
  # their double quotes reach the tool through the command line as \" (see $InnerArg below)
  function TomlS([string]$v) { '"' + ($v.Replace('\', '/').Replace('"', '\"')) + '"' }
  $McpArgs = "--skip-git-repo-check -c $(Q ('mcp_servers.kalmido.command=' + (TomlS $PsHost))) -c $(Q ('mcp_servers.kalmido.args=[' + ((@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $McpJ) | ForEach-Object { TomlS $_ }) -join ',') + ']'))"
}
if ($DryRun) { Say (M 'dry_mcp' @($McpJ, $Py, ($pyArgsJ -join ' '))) }
elseif ($Tool -eq 'codex') {
  # 2.575.0 (#3948): comments behind values (" # ...") are cut off as in the launcher: a quoted value keeps its content, an
  # unquoted one loses everything from the first whitespace + "#"
  $WrapLoop = @'
foreach ($l in Get-Content -LiteralPath @@ENVF@@) { if ($l -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $k = $Matches[1]; $v = $Matches[2].Trim(); if ($v -match '^"([^"]*)"(\s+#.*)?$' -or $v -match "^'([^']*)'(\s+#.*)?$") { $v = $Matches[1] } else { $v = $v -replace '\s+#.*$', '' }; [Environment]::SetEnvironmentVariable($k, $v, 'Process') } }
'@
  $w = @('# 2.391.0 (#3359): the Kalmido MCP server for Codex CLI, with the env file of this agent',
         $WrapLoop.Replace('@@ENVF@@', (Q $EnvF)),
         "& $(Q $Py) $(($pyArgsJ | ForEach-Object { Q $_ }) -join ' ')")
  [IO.File]::WriteAllLines($McpJ, $w)
}
else {
  $mcp = @{ mcpServers = @{ kalmido = @{ command = $Py; args = $pyArgsJ; env = @{ KALMIDO_ENV_FILE = $EnvF } } } } | ConvertTo-Json -Depth 5
  [IO.File]::WriteAllText($McpJ, $mcp)
}
if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $Dir | Out-Null }

# kalmido-setup-step: claude_md
# 2.306.0 E (#2927): a CLAUDE.md for the project folder from mcp/CLAUDE.template.md (the rules between its markers) when the
# folder has none yet -- never overwritten
$ClaudeMd = Join-Path $Dir 'CLAUDE.md'
$ClaudeNew = $false
$Tpl = Join-Path $Inst 'CLAUDE.template.md'
if ((Test-Path -LiteralPath $ClaudeMd) -or (Test-Path -LiteralPath (Join-Path (Join-Path $Dir '.claude') 'CLAUDE.md'))) { Say (M 'claude_kept' @($ClaudeMd)) }
elseif ($DryRun) { Say (M 'dry_claude' @($ClaudeMd)) }
elseif (Test-Path -LiteralPath $Tpl) {
  $t = [IO.File]::ReadAllText($Tpl)
  $ma = '<!-- kalmido-agent-rules:start -->'; $mb = '<!-- kalmido-agent-rules:end -->'
  $a = $t.IndexOf($ma); $b = $t.IndexOf($mb)
  if ($a -ge 0 -and $b -gt $a) {
    $head = "# Rules for this project`n`n" +
            "<!-- Created by the Kalmido agent setup. Add your own rules here: what this agent works on, and, to narrow it`n" +
            "further, the Kalmido account ids allowed to give it orders. The launcher's fixed rules come first in every run and`n" +
            "this file cannot weaken them. -->`n`n"
    # 2.1367.0 (#2700): the template "Software development" adds its block (between its markers in the template file)
    $sw = ''
    $sa = $t.IndexOf('<!-- kalmido-template-software:start -->'); $sbm = '<!-- kalmido-template-software:end -->'; $sb = $t.IndexOf($sbm)
    if ($Template -eq 'software' -and $sa -ge 0 -and $sb -gt $sa) { $sw = "`n" + $t.Substring($sa, $sb + $sbm.Length - $sa) + "`n" }
    [IO.File]::WriteAllText($ClaudeMd, $head + $t.Substring($a, $b + $mb.Length - $a) + "`n" + $sw)
    Say (M 'claude_new' @($ClaudeMd))
    $ClaudeNew = $true
  }
}

# kalmido-setup-step: template
# 2.1367.0 (#2700): the template "Software development": its rules went into a new CLAUDE.md above; an existing CLAUDE.md
# is never changed, the rules land next to it as CLAUDE.software.md (a proposal, only when there is none); BRIEF-TEMPLATE.md
# only when there is none. Nothing here overwrites or deletes a file of the project.
function TplPut([string]$m, [string]$file, [string]$head) {  # -> 'new', 'kept' or '' (no block in the template file)
  $t = [IO.File]::ReadAllText($Tpl)
  $ms = "<!-- ${m}:start -->"; $me = "<!-- ${m}:end -->"
  $a = $t.IndexOf($ms); $b = $t.IndexOf($me)
  if ($a -lt 0 -or $b -lt $a) { return '' }
  if (Test-Path -LiteralPath $file) { return 'kept' }
  $body = if ($m -eq 'kalmido-template-brief') { $t.Substring($a + $ms.Length, $b - $a - $ms.Length).Trim("`n", "`r") } else { $t.Substring($a, $b + $me.Length - $a) }
  $fs = [IO.File]::Open($file, [IO.FileMode]::CreateNew)  # never over a file that appeared meanwhile
  try { $wr = New-Object IO.StreamWriter($fs, (New-Object Text.UTF8Encoding($false))); $wr.Write($head + $body + "`n"); $wr.Flush() } finally { $fs.Dispose() }
  return 'new'
}
if ($Template -eq 'software') {
  $Brief = Join-Path $Dir 'BRIEF-TEMPLATE.md'
  if ($DryRun) { Say (M 'dry_tpl' @($Brief)) }
  elseif (Test-Path -LiteralPath $Tpl) {
    if ($ClaudeNew) { Say (M 'tpl_claude') }
    else {
      $Prop = Join-Path $Dir 'CLAUDE.software.md'
      $head = "# Proposal: rules for building software`n`n<!-- From the template Software development of the Kalmido agent setup. This project already had a CLAUDE.md, which stays as`nit is: copy what fits from here into it, then delete this file. -->`n`n"
      switch (TplPut 'kalmido-template-software' $Prop $head) { 'new' { Say (M 'tpl_prop' @($Prop)) } 'kept' { Say (M 'tpl_propkept' @($Prop)) } }
    }
    switch (TplPut 'kalmido-template-brief' $Brief '') { 'new' { Say (M 'tpl_brief' @($Brief)) } 'kept' { Say (M 'tpl_briefkept' @($Brief)) } }
  }
}

# kalmido-setup-step: harden
# 2.1367.0 (#6457): Claude Code's deny rules for this project folder in .claude\settings.local.json (this computer only, not
# in the repository): no WebFetch / WebSearch, no Read of ~/.kalmido and of the env file, no Edit of the env file. Entries
# already there stay, a second setup adds nothing twice; the person may take the web rules out again (every run's settings
# keep the file rules, mcp/agent_run.py secret_deny_rules). Claude Code matches Windows paths as //c/Users/...
if ($Tool -ne 'codex') {
  $HSet = Join-Path (Join-Path $Dir '.claude') 'settings.local.json'
  if ($DryRun) { Say (M 'dry_harden' @($HSet)) }
  else {
    $ep = ([IO.Path]::GetFullPath($EnvF)) -replace '\\', '/'
    if ($ep -match '^([A-Za-z]):/') { $ep = '/' + $Matches[1].ToLower() + $ep.Substring(2) }
    $rules = @('WebFetch', 'WebSearch', 'Read(~/.kalmido/**)', "Read(/$ep)", "Edit(/$ep)")
    try {
      $d = if (Test-Path -LiteralPath $HSet) { [IO.File]::ReadAllText($HSet) | ConvertFrom-Json } else { New-Object PSObject }
      if ($null -eq $d) { $d = New-Object PSObject }
      if (-not ($d -is [PSCustomObject])) { throw 'not an object' }
      if (-not $d.PSObject.Properties['permissions']) { $d | Add-Member -NotePropertyName permissions -NotePropertyValue (New-Object PSObject) }
      if (-not ($d.permissions -is [PSCustomObject])) { throw 'permissions is not an object' }
      if (-not $d.permissions.PSObject.Properties['deny']) { $d.permissions | Add-Member -NotePropertyName deny -NotePropertyValue @() }
      if ($null -ne $d.permissions.deny -and -not ($d.permissions.deny -is [array])) { throw 'deny is not a list' }
      $deny = @($d.permissions.deny | Where-Object { $null -ne $_ })
      foreach ($x in $rules) { if ($deny -notcontains $x) { $deny += $x } }
      $d.permissions.deny = $deny
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $HSet) | Out-Null
      [IO.File]::WriteAllText("$HSet.new", ($d | ConvertTo-Json -Depth 20) + "`n")
      Move-Item -LiteralPath "$HSet.new" -Destination $HSet -Force
      Say (M 'harden' @($HSet))
    } catch { Say (M 'harden_fail' @($HSet)) }
  }
}

# kalmido-setup-step: autostart
Step (M 's_auto')
$PsExe = (Get-Process -Id $PID).Path
$Log = Join-Path $Inst 'agent.log'
$Inner = "Set-Location -LiteralPath $(Q $Dir); & $(Q (Join-Path $Inst 'agent_launcher.ps1')) -e $(Q $EnvF) --events -- $(Q $(if ($Agent) { $Agent } else { $Cmd })) $McpArgs *>> $(Q $Log)"
$InnerArg = $Inner.Replace('"', '\"')  # 2.575.0 (#3948): double quotes inside -Command "..." (TOML strings of the Codex arguments)
$PsArgs = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$InnerArg`""
# 2.443.0 (#2940): the Startup folder has no restart of its own: this loop does what RestartSec=30 / ThrottleInterval do in setup.sh
$LoopArgs = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"while (`$true) { $InnerArg; Start-Sleep -Seconds 30 }`""
if ($NoAutostart) { Say (M 'noauto'); Say "  $Inner" }
else {
  Stop-Autostart
  if ($DryRun) { Say (M 'dry_task' @($TaskName, $env:USERNAME, $PsExe, $PsArgs)) }
  else {
    $done = $false
    try {
      $user = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
      $action = New-ScheduledTaskAction -Execute $PsExe -Argument $PsArgs -WorkingDirectory $Dir
      $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
      $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -Hidden
      $prin = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
      Register-ScheduledTask -TaskPath '\Kalmido\' -TaskName $TaskName -Action $action -Trigger $trigger -Settings $set -Principal $prin -Force | Out-Null
      Start-ScheduledTask -TaskPath '\Kalmido\' -TaskName $TaskName
      $done = $true
      Say (M 'taskok' @($TaskName, $Log))
    } catch { Say (M 'taskfail' @($_.Exception.Message)) }
    if (-not $done) {
      New-Item -ItemType Directory -Force -Path $StartupDir | Out-Null
      [IO.File]::WriteAllLines($StartupCmd, @('@echo off', "start `"`" /min `"$PsExe`" $LoopArgs"))
      Start-Process -FilePath $PsExe -ArgumentList $LoopArgs -WindowStyle Hidden
      Say (M 'startupok' @($StartupCmd, $Log))
    }
  }
}

# kalmido-setup-step: done
Step (M 's_done')
Say (M 'done1')
Say (M 'done2' @($Url, (Q $Dir)))
