import assert from "node:assert/strict";
import test from "node:test";

import { filterSkillMentions, parseSkillMention, selectedSkillMentionState } from "./skill-mention.js";

const skills = [
  {
    name: "codex-security:attack-path-analysis",
    description: "Perform attack-path analysis for a security finding.",
    source: "plugin",
    version: "0.1.0",
    argument_hint: "",
  },
  {
    name: "research",
    description: "Research a topic using primary sources.",
    source: "builtin",
    version: "0.1.0",
    argument_hint: "",
  },
];

test("@ opens a skill picker and filters by name or description", () => {
  assert.deepEqual(
    filterSkillMentions(skills, "@").map((skill) => skill.name),
    ["codex-security:attack-path-analysis", "research"],
  );
  assert.deepEqual(
    filterSkillMentions(skills, "@attack").map((skill) => skill.name),
    ["codex-security:attack-path-analysis"],
  );
  assert.deepEqual(
    filterSkillMentions(skills, "@primary").map((skill) => skill.name),
    ["research"],
  );
  assert.deepEqual(filterSkillMentions(skills, "@research investigate the API"), []);
});

test("parses a selected @skill mention and its prompt", () => {
  assert.deepEqual(parseSkillMention("@research investigate the API", skills), {
    skill: skills[1],
    prompt: "investigate the API",
  });
  assert.equal(parseSkillMention("@missing investigate", skills), null);
});

test("builds the shared state used after selecting a skill mention", () => {
  assert.deepEqual(selectedSkillMentionState(skills[1]), {
    inputValue: "@research ",
    pendingSkill: skills[1],
    skillMentionIndex: 0,
    statusLine: "",
  });
});
