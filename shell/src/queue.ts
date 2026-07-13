export const MAX_QUEUED_MESSAGES = 3;

export type QueuedMessage = {
  id: string;
  text: string;
  skillName?: string;
};
