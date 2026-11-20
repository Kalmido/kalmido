# Hauswörter (deutsche Oberfläche)

Ein Wort hat genau eine Bedeutung, eine Sache genau einen Namen. Gilt für Listen/Projekte (#5441),
Kalender (#5467), Büro (#5454) und Wissen (#6091). Neue Texte halten sich daran; abweichende Alt-Texte werden beim
Anfassen angeglichen. Geändert wird die Übersetzung in `static/i18n/de.json`; ein Schlüssel mit zwei
Bedeutungen bekommt einen Kontext (`Event|calendar`, `People|event`).

| Sache | Hauswort | Nicht verwenden |
|---|---|---|
| Eintrag im Kalender | Termin | Ereignis, Event |
| Ereignis in Benachrichtigungen/Agenten | Ereignis | (dort richtig, kein Termin) |
| Von außen eingebundener Kalender (ICS) | Abonnierter Kalender | Abo, Kalender-Abo, Kalender-Abonnement |
| Eigener Export-Link des Kalenders | Kalender-Link | Kalender-Abo, Öffentlicher Kalender-Link |
| Rolle lesend / schreibend (Kalender, in Sätzen) | kann ansehen / kann bearbeiten | Nur lesen |
| Rolle lesend in Projekten/Organisationen (Auswahl neben Admin/Mitglied) | Nur ansehen | Nur lesen, Betrachter |
| Zustand ohne Schreibrecht | nur ansehen | nur lesen |
| Frei/Belegt | belegt | beschäftigt |
| Eigene Wiederholung | Eigene… | Benutzerdefiniert |
| Zusage zu einem Termin | Zusagen / Vielleicht / Ablehnen; Status Zugesagt | Annehmen |
| Teilnehmende am Termin | Gästeliste | Personen |
| Gruppe der Seitenleiste für Projekte | Projekte | Listen |
| Aufgabe ohne Abschnitt | Ohne Abschnitt | Nicht zugeordnet |
| Aufgabe ohne Zuständige | Ohne Zuständige | Nicht zugeordnet |
| Aufgabe selbst nehmen | Selbst übernehmen | Übernehmen |
| Vorschlag/Einstellung anwenden | Übernehmen | |
| Board-Zeilen | Gruppieren nach | Zeilen, Swimlanes |
| Block der Projektseite mit Durchlauf-/Zykluszeit | Durchlauf | Fluss, Flow |
| Teil „Projekt bearbeiten“ mit Projekttyp, Tickets, Sprints, Feldern | Was das Projekt kann | Projekt-Funktionen |
| Teil „Projekt bearbeiten“ mit Formularen, Software, Webhooks, Regeln | Formulare, Regeln & Anbindungen | Formulare & Software |
| Eigenschaften ohne eigene Abweichung | Wie vom Projekttyp vorgegeben | Wie der Projekttyp |
| Entfernen mit Rückgängig | Löschen (Papierkorb: „In den Papierkorb“) | Entfernen, Gelöscht/Archiviert für dasselbe |
| Neues Element in einer Liste (Eingabefeld in der Liste) | hinzufügen | übernehmen |
| Hauptknopf eines Dialogs, der etwas Neues anlegt (#6373) | Anlegen (en: Create) | Erstellen, Speichern, Hinzufügen |
| Hauptknopf beim Bearbeiten von Bestehendem | Speichern | |
| Etwas Bestehendes kommt dazu (Person zu Projekt, Kalender aus CalDAV) | Hinzufügen | Anlegen |
| Bereich mit den Seiten (Seitenleiste, Titel, Pfad) | Wissen | Wissensseiten, Wiki |
| Eine Seite darin | Seite (quer über Bereiche: Seite unter Wissen) | Wissensseite |
| Privat / Organisation unter Wissen | Arbeitsbereich | Bereich, Wissensbereich |
| Alle Seiten eines Arbeitsbereichs für einen Agenten | alle Seiten (teilen) | gesamter Wissensbereich |
| Gespeicherter Stand einer Seite, Konfliktseite | Version | Fassung |
| Stichwort einer Seite (#…) | Schlagwort | Tag |
| Nur dieses Gerät bearbeitet nicht | Bearbeiten sperren (dieses Gerät) | Nur ansehen (das ist die Rolle) |
| Darstellung der Seiten | Lesestil, Stil „Schlicht“ | Lese-Stil, Klar |
| Im Browser verschlüsselter Arbeitsbereich | verschlüsselt (im Browser) | Ende-zu-Ende, gesperrt |
| Markdown-Feld / ZIP-Export | Als reinen Text bearbeiten / Alle Seiten herunterladen, aus einem Archiv importieren | Markdown, ZIP |

Fachwörter (Kanban, Swimlanes, WIP, Backlog) stehen nur dort, wo die Funktion eingeschaltet ist: die Ansicht
„Kanban“ erscheint nur mit dem Modul Kanban, WIP-Grenzen nur an Spalten mit Grenze, Backlog nur mit Sprints und als Abschnitt im Software-Projekt.
„Mindmap“ und „Zeitstrahl“ gelten als Alltagswörter (#5481).
Technikwörter (ICS, iCal, CalDAV, Basis-URL, „Erlaubte interne Hosts“, IANA-Zonen) nur in den
Einstellungen für Fortgeschrittene.

Rollen (#5481, 2.831): die Leserolle in Projekten und Organisationen heißt „Nur ansehen“, im Kalender in Sätzen
„kann ansehen“; „Nur lesen“ gibt es in der deutschen Oberfläche der Listen nicht mehr.

Dialoge (#6373, entschieden 16.11.2026):
1. Ein Dialog, der etwas Neues anlegt, hat den Hauptknopf „Anlegen“ (englisch „Create“); „Speichern“ nur beim Bearbeiten,
   „Hinzufügen“ nur, wenn etwas Bestehendes dazukommt.
2. Ein Dialog, der selbst speichert, schließt mit dem Hauptknopf „Fertig“; ein reiner Lese-Dialog mit dem schlichten Knopf
   „Schließen“.
3. Das Schließen-Kreuz oben rechts haben alle großen Dialoge (Blatt über mehr als die halbe Fensterhöhe) immer, kleine
   Frage-Dialoge (askConfirm / askPrompt) nie. Das Kreuz setzt `static/js/dialogs.js` (dlgCross) selbst; ein Dialog mit
   eigenem Kreuz behält seins. Ein Frage-Dialog nennt im Knopf das Verb (`ok:`), nicht „OK“.
Geprüft in `tools/check_rules.py` (Regel dialog-verb): Bearbeiten-oder-neu ohne „Create“, Frage-Dialoge ohne eigenen
Knopftext, die deutsche Übersetzung von „Create“.
