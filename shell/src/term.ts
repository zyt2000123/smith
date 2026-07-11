/**
 * Clear the visible screen and scrollback before a transcript-replacing action
 * (/clear, /new, /resume). <Static> output is append-only, so replacing the
 * conversation requires wiping the terminal and remounting Static via epoch.
 */
export function clearTerminal(): void {
  process.stdout.write("\x1b[2J\x1b[3J\x1b[H");
}
