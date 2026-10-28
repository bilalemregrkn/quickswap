# Records assets/setup.gif with https://github.com/charmbracelet/vhs - run from the repo root: vhs assets/setup.tape
# Uses the repo's .venv and a throwaway config. Display UUIDs and temp paths are masked in the output.
Output assets/setup.gif

Set Shell zsh
Set Theme "GitHub Dark"
Set FontSize 20
Set Width 1200
Set Height 620
Set Padding 28
Set TypingSpeed 55ms

Hide
Type "export PATH=$PWD/.venv/bin:$PATH QUICKSWAP_CONFIG=$(mktemp -d)/config.toml PROMPT='%F{245}~ %#%f '"
Enter
Type `quickswap() { command quickswap "$@" 2>&1 | sed -E -e 's/[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX/g' -e "s#$QUICKSWAP_CONFIG#~/.config/quickswap/config.toml#g"; }`
Enter
Type "clear"
Enter
Sleep 500ms
Show

Sleep 600ms
Type "quickswap discover"
Sleep 300ms
Enter
Sleep 4s

Type "quickswap init"
Sleep 300ms
Enter
Sleep 4500ms

Type "quickswap status"
Sleep 300ms
Enter
Sleep 5s
