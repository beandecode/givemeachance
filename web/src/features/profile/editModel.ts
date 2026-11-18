import { text, textList } from "@/lib/format";

import type { MasterProfile } from "./profileModel";
import { itemList, obj } from "./profileModel";

export interface ExperienceDraft {
  title: string;
  company: string;
  location: string;
  start_date: string;
  end_date: string;
  highlights: string;
  tech_stack: string;
  /** Fields the form doesn't edit (achievements, employment type, …) are carried over untouched. */
  rest: Record<string, unknown>;
}

export interface ProfileDraft {
  name: string;
  current_title: string;
  location: string;
  years_experience: string;
  email: string;
  phone: string;
  links: string;
  summary: string;
  highlights: string;
  core_skills: string;
  experiences: ExperienceDraft[];
  education: string;
  certifications: string;
  languages: string;
  target_roles: string;
  preferred_locations: string;
  work_authorization: string;
}

const lines = (values: string[]) => values.join("\n");
const splitLines = (value: string) =>
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
const splitCommas = (value: string) =>
  value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);

export function emptyExperience(): ExperienceDraft {
  return {
    title: "",
    company: "",
    location: "",
    start_date: "",
    end_date: "",
    highlights: "",
    tech_stack: "",
    rest: {},
  };
}

export function toDraft(profile: MasterProfile): ProfileDraft {
  const identity = obj(profile.identity);
  const contact = obj(identity.contact);
  const preferences = obj(profile.preferences);
  return {
    name: text(identity.name),
    current_title: text(identity.current_title),
    location: text(identity.location),
    years_experience: text(identity.years_experience),
    email: text(contact.email),
    phone: text(contact.phone),
    links: lines(textList(contact.links)),
    summary: text(profile.profile_summary),
    highlights: lines(textList(profile.career_highlights)),
    core_skills: textList(profile.core_skills).join(", "),
    experiences: (Array.isArray(profile.experiences) ? profile.experiences : []).map((raw) => {
      const { title, company, location, start_date, end_date, highlights, tech_stack, ...rest } = obj(raw);
      return {
        title: text(title),
        company: text(company),
        location: text(location),
        start_date: text(start_date),
        end_date: text(end_date),
        highlights: lines(textList(highlights)),
        tech_stack: textList(tech_stack).join(", "),
        rest,
      };
    }),
    education: lines(itemList(profile.education)),
    certifications: lines(itemList(profile.certifications)),
    languages: itemList(profile.languages).join(", "),
    target_roles: textList(preferences.target_roles).join(", "),
    preferred_locations: textList(preferences.preferred_locations).join(", "),
    work_authorization: text(preferences.work_authorization),
  };
}

/** Apply the form to a copy of the original profile, keeping every field the form doesn't show. */
export function fromDraft(original: MasterProfile, draft: ProfileDraft): MasterProfile {
  const identity = obj(original.identity);
  const contact = obj(identity.contact);
  const preferences = obj(original.preferences);
  const education = splitLines(draft.education);
  const certifications = splitLines(draft.certifications);
  const languages = splitCommas(draft.languages);
  const unchanged = (key: string, next: string[]) =>
    itemList(original[key]).join("\n") === next.join("\n") ? original[key] : next;
  return {
    ...original,
    identity: {
      ...identity,
      name: draft.name.trim(),
      current_title: draft.current_title.trim(),
      location: draft.location.trim(),
      years_experience: draft.years_experience.trim(),
      contact: {
        ...contact,
        email: draft.email.trim(),
        phone: draft.phone.trim(),
        links: splitLines(draft.links),
      },
    },
    profile_summary: draft.summary.trim(),
    career_highlights: splitLines(draft.highlights),
    core_skills: splitCommas(draft.core_skills),
    experiences: draft.experiences.map((experience) => ({
      ...experience.rest,
      title: experience.title.trim(),
      company: experience.company.trim(),
      location: experience.location.trim(),
      start_date: experience.start_date.trim(),
      end_date: experience.end_date.trim(),
      highlights: splitLines(experience.highlights),
      tech_stack: splitCommas(experience.tech_stack),
    })),
    // Structured entries from the model stay as they were unless the text actually changed.
    education: unchanged("education", education),
    certifications: unchanged("certifications", certifications),
    languages: unchanged("languages", languages),
    preferences: {
      ...preferences,
      target_roles: splitCommas(draft.target_roles),
      preferred_locations: splitCommas(draft.preferred_locations),
      work_authorization: draft.work_authorization.trim(),
    },
  };
}
