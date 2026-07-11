const EMOJI_ICON =
  /(?:(?:\p{Extended_Pictographic}(?:\uFE0E|\uFE0F|\p{Emoji_Modifier})?)(?:\u200D(?:\p{Extended_Pictographic}(?:\uFE0E|\uFE0F|\p{Emoji_Modifier})?))*|\p{Regional_Indicator}{1,2}|[0-9#*]\uFE0F?\u20E3)[ \t]?/gu;
const EMOJI_ARTIFACT = /\uFE0E|\uFE0F|\u200D|\u20E3/g;

/** Removes decorative emoji from assistant text before terminal rendering. */
export function stripEmojiIcons(text: string): string {
  return text.replace(EMOJI_ICON, "").replace(EMOJI_ARTIFACT, "");
}
