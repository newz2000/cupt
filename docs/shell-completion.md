# Shell completion

Click provides static completion for cupt commands and options.

## Bash

```bash
eval "$(_CUPT_COMPLETE=bash_source cupt)"
```

To persist it, add the line above to `~/.bashrc`.

## Zsh

```zsh
eval "$(_CUPT_COMPLETE=zsh_source cupt)"
```

To persist it, add the line above to `~/.zshrc`.

## Fish

```fish
_CUPT_COMPLETE=fish_source cupt | source
```

To persist it, place the command in `~/.config/fish/config.fish`.
