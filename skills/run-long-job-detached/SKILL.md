---
name: run-long-job-detached
description: Run a script that takes longer than about 30 minutes so it survives session restarts and background-agent deaths, and still reports its result when it finishes.
trigger: long crawl, job over 30 minutes, survive session restart, background agent died, send result when done, detach a job, run overnight, resumable crawl
---

# Run a long job detached, with a completion sender

Use when a job will outlive the session that starts it: a crawl, a backfill, a bulk render. Restarts kill background agents and the tmux session mid-task, so anything tied to the session or to an agent's Bash call is at risk. A two-hour crawl launched from an agent's Bash call will usually not finish.

## Steps

1. **Do not run the job inside an agent or in the session's own Bash call.** Start it from a small wrapper script that returns at once.
2. **Take a lock first.** If a PID file exists and `kill -0 <pid>` succeeds, log "skip: previous run still alive" and exit 0. One run at a time, and a second launch is harmless.
3. **Launch with `setsid nohup <cmd> >> <log> 2>&1 < /dev/null &`**, then write `$!` to the lock file. `setsid` gives the job its own session with PPID 1, so a tmux or agent kill does not reach it.
4. **Make the job resumable before you need it.** Cache fetched pages or rows on disk with a TTL (24 hours is a sensible start for a crawl), so running the wrapper again continues instead of restarting.
5. **Report the result.** Proven pattern: the job sends its own result as its last step (a `--send` flag on the job). Alternative, less tested: start a second detached script that waits on the job's PID, then sends the result (a digest to chat, the result file path) and drops a marker file. Wait on the PID with a `kill -0` and sleep loop, not on `pgrep -f <script name>`: a process-kill guard may block pattern-based process matching, and a PID check is narrower.
6. **When it finishes, the sender writes one log line and the marker file.** A later session checks the marker, not the live process.
7. **For a recurring run, put the wrapper in the scheduler as a shell task.** It then costs no tokens and spawns no session.

## Caveats

- If the job ends while the sender is dead, nothing is sent. A missing marker file the next morning is the signal, not an error message.
- Keep secrets out of the wrapper. The sender should read its bot token from the environment or a gitignored `.env` at run time.
- Under about 10 minutes, a foreground run with an explicit timeout is simpler.

## Output

The wrapper prints "launched pid N, log <path>". A finished job leaves four things: the log, the lock file (PID), the marker file and the result message.
