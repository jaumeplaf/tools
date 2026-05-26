# Identify UE5 WP Actor
Tool to translate UE5 WP Actors from their custom ID to their actual display name.

# Sourcetree:
·Download the .exe or clone the repo

·Go to Tools->**Options**->Custom Actions->Add. 

·Set "Open in a separate window" **true**, "Show full output" **true**, "Run command silently" **false**. Link the **.exe** to the "Script to run". Set Parameters: "**$REPO $FILE --pause**".

·Use it by **right clicking** the selected files->Custom Actions->IdentifyUE5_WP_Actor

<img width="677" height="596" alt="Screenshot 2026-05-26 074957" src="https://github.com/user-attachments/assets/975e00ae-325b-4099-b0f9-f638a1866f21" />
<img width="417" height="296" alt="image" src="https://github.com/user-attachments/assets/ae95468e-cf78-425f-a13e-7f7738643dc8" />
<img width="703" height="393" alt="Screenshot 2026-05-26 075349" src="https://github.com/user-attachments/assets/20a63107-6d54-4c60-a7a6-9498aaf7b19f" />
<img width="466" height="118" alt="Screenshot 2026-05-26 075423" src="https://github.com/user-attachments/assets/768c7b0e-befb-4e0c-a20b-a629ebcaca01" />

# Github desktop
·Copy the .exe to the repository root (or keep it anywhere you want).

·Go to Repository->**Open in Command Prompt**

·If the .exe is in the repo root, run: **resolve_actor.exe . --all-changed --pause**

·If the .exe is outside the repo, run it with full path: **"C:\Full\Path\To\resolve_actor.exe" . --all-changed --pause**

<img width="248" height="247" alt="Screenshot 2026-05-26 075931" src="https://github.com/user-attachments/assets/bfb178c9-731c-4e51-b651-6c4ddeeb05af" />
<img width="802" height="95" alt="Screenshot 2026-05-26 075915" src="https://github.com/user-attachments/assets/637e54b2-7fc8-4f5a-b068-bbf3e25f3d43" />
