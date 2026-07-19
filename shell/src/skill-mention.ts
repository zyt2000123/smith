import type { SkillSummary } from "./api.js";

export function isSkillMentionQuery(input: string): boolean {
  return /^@\S*$/.test(input);
}

export function isSkillEnabled(skill: SkillSummary): boolean {
  return skill.enabled !== false;
}

export function filterSkillMentions(skills: SkillSummary[], input: string): SkillSummary[] {
  if (!isSkillMentionQuery(input)) return [];

  const query = input.slice(1).toLowerCase();
  const enabledSkills = skills.filter(isSkillEnabled);
  if (!query) return enabledSkills;
  return enabledSkills.filter((skill) =>
    `${skill.name} ${skill.description} ${skill.source}`.toLowerCase().includes(query),
  );
}

export function filterSkills(skills: SkillSummary[], query: string): SkillSummary[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return skills;
  return skills.filter((skill) =>
    `${skill.name} ${skill.description} ${skill.source}`.toLowerCase().includes(normalized),
  );
}

export function parseSkillMention(raw: string, skills: SkillSummary[]): { skill: SkillSummary; prompt: string } | null {
  const match = raw.trim().match(/^@(\S+)(?:\s+([\s\S]+))?$/);
  if (!match) return null;

  const skill = skills.find((candidate) => candidate.name === match[1] && isSkillEnabled(candidate));
  return skill ? { skill, prompt: match[2]?.trim() || "" } : null;
}

export function selectedSkillMentionState(skill: SkillSummary) {
  return {
    inputValue: `@${skill.name} `,
    pendingSkill: skill,
    skillMentionIndex: 0,
    statusLine: "",
  };
}
