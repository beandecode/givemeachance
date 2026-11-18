import { isBlank, text, textList } from "@/lib/format";

/** The Master Profile is free-form JSON; these helpers read it defensively. */
export type MasterProfile = Record<string, unknown>;

export interface Experience {
  title: string;
  company: string;
  location: string;
  startDate: string;
  endDate: string;
  duration: string;
  highlights: string[];
  techStack: string[];
}

export interface MissingItem {
  field: string;
  question: string;
  priority: "high" | "medium" | "low";
}

export function obj(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/** Strings stay as they are; objects (e.g. education entries from the model) become "a · b · c". */
export function itemText(value: unknown): string {
  if (typeof value === "string") return text(value);
  const values = Object.values(obj(value)).map(text).filter(Boolean);
  return values.join(" · ");
}

export function itemList(value: unknown): string[] {
  return list(value).map(itemText).filter(Boolean);
}

export function readProfile(profile: MasterProfile) {
  const identity = obj(profile.identity);
  const contact = obj(identity.contact);
  const preferences = obj(profile.preferences);
  const skillMatrix = obj(profile.skill_matrix);
  return {
    name: text(identity.name),
    currentTitle: text(identity.current_title),
    location: text(identity.location),
    yearsExperience: text(identity.years_experience),
    email: text(contact.email),
    phone: text(contact.phone),
    links: textList(contact.links),
    summary: text(profile.profile_summary),
    highlights: textList(profile.career_highlights),
    coreSkills: textList(profile.core_skills),
    skillGroups: Object.entries(skillMatrix)
      .map(([group, skills]) => ({ group, skills: textList(skills) }))
      .filter((entry) => entry.skills.length > 0),
    experiences: list(profile.experiences).map((raw): Experience => {
      const entry = obj(raw);
      return {
        title: text(entry.title),
        company: text(entry.company),
        location: text(entry.location),
        startDate: text(entry.start_date),
        endDate: text(entry.end_date),
        duration: text(entry.duration),
        highlights: [...textList(entry.highlights), ...textList(entry.achievements)],
        techStack: textList(entry.tech_stack),
      };
    }),
    projects: list(profile.projects).map((raw) => {
      const entry = obj(raw);
      return {
        name: text(entry.name),
        role: text(entry.role),
        summary: text(entry.summary),
        impact: textList(entry.impact),
        techStack: textList(entry.tech_stack),
      };
    }),
    education: itemList(profile.education),
    certifications: itemList(profile.certifications),
    languages: itemList(profile.languages),
    targetRoles: textList(preferences.target_roles),
    preferredLocations: textList(preferences.preferred_locations),
    workAuthorization: text(preferences.work_authorization),
    missing: list(profile.missing_information)
      .map((raw): MissingItem => {
        const entry = obj(raw);
        const priority = text(entry.priority).toLowerCase();
        return {
          field: text(entry.field),
          question: text(entry.question),
          priority: priority === "high" || priority === "low" ? priority : "medium",
        };
      })
      .filter((item) => item.field && item.question),
    completeness: typeof profile.completeness_score === "number" ? profile.completeness_score : null,
  };
}

export type ProfileView = ReturnType<typeof readProfile>;

export function dateRange(experience: Experience): string {
  if (experience.startDate || experience.endDate) {
    return `${experience.startDate || "?"} – ${experience.endDate || "Present"}`;
  }
  return experience.duration;
}

export function hasContent(value: unknown): boolean {
  return !isBlank(value);
}
