# HLL Discord status bots

One Node.js process can run any number of Discord bots. Configuration is read
from the `BOT_STAT_CONFIG_JSON` value in `.env`; each entry in `servers` owns one
Discord bot and one game-server query endpoint.

## Configure

Edit `.env` and fill the server-specific values:

- `id`: unique name used only in logs
- `enabled`: start this bot when `true`
- `discordToken`: token for this server's Discord bot application
- `source`: `crcon` (recommended here) or `gamedig`
- `crcon.baseUrl`: URL of that server's CRCON public-stats listener
- `crcon.publicInfoPath`: normally `/api/get_public_info`
- `crcon.timeoutMs`: HTTP timeout for one CRCON request

The public-info endpoint does not require a CRCON API key. When `source` is
`gamedig` instead, configure `game.type`, `game.host`, and `game.queryPort`.

Values from `defaults` may be overridden in any server object. For example:

```json
{
  "id": "vietnam",
  "enabled": true,
  "source": "crcon",
  "discordToken": "replace-me",
  "refreshIntervalMs": 60000,
  "statusTemplate": "Vietnam {players}/{maxPlayers} ⏳{timeRemaining} {map}",
  "crcon": {
    "baseUrl": "http://127.0.0.1:7001",
    "publicInfoPath": "/api/get_public_info",
    "timeoutMs": 5000
  }
}
```

Supported status placeholders are `{id}`, `{map}`, `{players}`, `{maxPlayers}`,
and `{timeRemaining}`. The remaining round time is formatted as `HH:MM:SS`;
`unknownTimeText` is used when the selected query source does not provide it.
The JSON may be formatted across multiple lines as long as the entire value
remains enclosed in single quotes.

CRCON's short map name is used for the Discord activity. `maxMapLength` limits
long fallback names and may be overridden per server.

After editing the configuration:

```sh
sudo systemctl restart bot_stat
sudo systemctl status bot_stat --no-pager
journalctl -u bot_stat -f
```

If one bot cannot log in or one game server cannot be queried, the other bots
continue running.
