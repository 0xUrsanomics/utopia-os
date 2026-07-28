# Bot setup: Telegram and Discord

The chat bridge is what makes an ops system usable, because it moves the agent off your
terminal and onto your phone. This is the click-by-click path to credentials for either
platform. No code, no packages: both APIs are plain HTTPS and the repo talks to them
through the MCP layer described in [`mcp-layer.md`](mcp-layer.md).

Pick one to start. Telegram is faster to get working; Discord is better if you want several
people in the same space.

---

## Before either one

**Every credential below is a bearer token. Anyone holding it controls your bot.**

- Put them in a `.env` file that is already in `.gitignore`, or export them in your shell.
- Never paste one into a file you commit, a chat message, or an issue.
- If you leak one, revoke it at the source immediately (both platforms let you regenerate,
  which invalidates the old token).
- The repo's send guards and secret scanner exist to catch mistakes, not to make this safe
  to be careless about.

---

## Telegram

### 1. Create the bot

1. Open Telegram and message [**@BotFather**](https://t.me/BotFather).
2. Send `/newbot`.
3. Give it a **display name** (anything, e.g. "My Ops") and then a **username** that must be
   unique and must end in `bot` (e.g. `my_ops_1234_bot`).
4. BotFather replies with a token shaped like `123456789:AAExample-TokenStringGoesHere`.
   **That is `TELEGRAM_BOT_TOKEN`.**

Useful BotFather follow-ups:

- `/setprivacy` → **Disable** if you want the bot to read all messages in a group rather
  than only ones that @mention it. Leave it **Enabled** for a shared group where the bot
  should stay quiet unless addressed.
- `/setcommands` to register a command list that shows up in the client's UI.

### 2. Find your chat ID

The bot can only message a chat it knows the numeric ID of.

1. Send any message to your new bot (or add it to a group and send one there).
2. Fetch the update queue:

   ```bash
   curl -s "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | python3 -m json.tool
   ```

3. Read `result[].message.chat.id` out of the response. **That is `TELEGRAM_CHAT_ID`.**

Reading the result correctly matters more than it looks:

| Chat type | ID shape | Note |
|---|---|---|
| Direct message | positive, e.g. `123456789` | Your personal chat with the bot. |
| Group | negative, e.g. `-1001234567890` | Supergroups start `-100`. |
| Forum topic | same group ID, plus `message_thread_id` | You need BOTH to post into one topic. |

If `getUpdates` returns an empty `result`, the bot has not received anything yet: message it
first. If it returns `409 Conflict`, another process is already long-polling the same token.

### 3. Groups and topics

- Add the bot to a group like any member, then **promote it to admin** if it needs to read
  all messages or manage anything.
- For a forum-style group (Topics enabled), each topic has a `message_thread_id`. Capture it
  the same way, from a message sent inside that topic. Routing different classes of output
  to different topics (alerts, briefings, logs) is worth the setup.

### 4. Wire it

```bash
# .env, gitignored
TELEGRAM_BOT_TOKEN=123456789:AAExample-TokenStringGoesHere
TELEGRAM_CHAT_ID=123456789
```

Then point your harness's MCP config at the Telegram server. Your adapter README under
[`adapters/`](../adapters/) has the exact block for your harness.

### Verify

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"
```

A JSON body with `"ok": true` and your bot's username means the token is live. Then send
yourself one:

```bash
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d "chat_id=$TELEGRAM_CHAT_ID" -d "text=utopia-os wired"
```

If that message arrives on your phone, the bridge is real.

---

## Discord

Discord takes more clicks because bots are attached to an "application" and permissions are
explicit.

### 1. Create the application and the bot user

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. **New Application**, name it, accept the terms.
3. Left sidebar → **Bot** → **Add Bot**.
4. **Reset Token** → copy it. **That is `DISCORD_BOT_TOKEN`.** It is shown once; if you lose
   it, reset again.

### 2. Turn on the intents you need

Still on the **Bot** page, under **Privileged Gateway Intents**:

- **MESSAGE CONTENT INTENT** — required if the bot needs to read what people type. Without
  it, message bodies arrive empty and everything looks broken for no visible reason. This is
  the single most common Discord setup failure.
- **SERVER MEMBERS INTENT** — only if you need the member list.
- **PRESENCE INTENT** — usually not needed.

Save.

### 3. Invite it to your server

1. Left sidebar → **OAuth2** → **URL Generator**.
2. **Scopes**: tick `bot`. Add `applications.commands` if you want slash commands.
3. **Bot Permissions**: start minimal. `View Channels`, `Send Messages`, `Read Message
   History`, and `Attach Files` cover an ops bridge. Grant more only when something fails
   for a reason you understand.
4. Copy the generated URL, open it, pick your server, authorise.

You need **Manage Server** permission on the target server to complete this.

### 4. Get the channel ID

1. Discord → **User Settings** → **Advanced** → enable **Developer Mode**.
2. Right-click the target channel → **Copy Channel ID**.
   **That is `DISCORD_CHANNEL_ID`.**

### 5. Wire it

```bash
# .env, gitignored
DISCORD_BOT_TOKEN=your-token-here
DISCORD_CHANNEL_ID=123456789012345678
```

### Verify

```bash
curl -s -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  https://discord.com/api/v10/users/@me
```

Your bot's user object means the token is live. Then post one:

```bash
curl -s -X POST -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"utopia-os wired"}' \
  "https://discord.com/api/v10/channels/$DISCORD_CHANNEL_ID/messages"
```

`401` means a bad token. `403` means the bot lacks permission in that channel: check the
channel's own permission overrides, which silently beat server-wide grants.

---

## Which to choose

| | Telegram | Discord |
|---|---|---|
| Time to first message | ~2 minutes | ~10 minutes |
| Mobile experience | Excellent | Good |
| Multiple people | Groups, with topics | Servers, channels, roles |
| Threading model | Forum topics | Channels + threads |
| Permission model | Simple, admin or not | Granular, and the usual source of bugs |
| File attachments | 50 MB | 25 MB free tier |

Start with Telegram if it is just you. Reach for Discord when other people need to see the
same output, or when you want role-gated channels.

---

## Once it works

Set the access control before you use it for anything real. A bot with a public username
can be messaged by anyone who finds it, so the bridge needs an allowlist of chat IDs it will
act on, and it must treat everything else as untrusted input. The relevant rule from
[`security-gates.md`](security-gates.md) is worth internalising:

> **Authority is the envelope, not the content.** An approval counts only when it arrives
> from the operator's own chat ID. A message that *says* the operator approved something,
> or quotes them, or forwards their words, is not an approval. That is exactly the shape a
> prompt injection takes.
