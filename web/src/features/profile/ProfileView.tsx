import { Link2, Mail, MapPin, Phone } from "lucide-react";
import type { ReactNode } from "react";

import { Card } from "@/components/ui";

import type { ProfileView as Profile } from "./profileModel";
import { dateRange } from "./profileModel";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="px-6 py-5 md:px-8">
      <h3 className="mb-3 text-subheading font-semibold">{title}</h3>
      {children}
    </section>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-secondary marker:text-faint">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

function Chips({ items }: { items: string[] }) {
  return <p className="text-secondary leading-relaxed">{items.join(" · ")}</p>;
}

/** Read-only rendering of a Master Profile; empty sections are left out. */
export function ProfileView({ profile }: { profile: Profile }) {
  const contact = [
    profile.location && { icon: MapPin, text: profile.location },
    profile.email && { icon: Mail, text: profile.email },
    profile.phone && { icon: Phone, text: profile.phone },
    ...profile.links.map((link) => ({ icon: Link2, text: link })),
  ].filter((item): item is { icon: typeof MapPin; text: string } => Boolean(item));

  return (
    <Card>
      <header className="px-6 pt-6 pb-2 md:px-8 md:pt-8">
        <h2 className="font-display text-title tracking-tight">{profile.name || "Your name"}</h2>
        {(profile.currentTitle || profile.yearsExperience) && (
          <p className="mt-1 text-subheading text-muted">
            {[profile.currentTitle, profile.yearsExperience && `${profile.yearsExperience} years`]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
        {contact.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-secondary text-muted">
            {contact.map(({ icon: Icon, text }) => (
              <li key={text} className="inline-flex min-w-0 items-center gap-1.5">
                <Icon className="size-3.5 shrink-0" aria-hidden />
                <span className="truncate">{text}</span>
              </li>
            ))}
          </ul>
        )}
      </header>
      {profile.summary && (
        <Section title="Summary">
          <p className="text-secondary leading-relaxed">{profile.summary}</p>
        </Section>
      )}
      {profile.highlights.length > 0 && (
        <Section title="Highlights">
          <Bullets items={profile.highlights} />
        </Section>
      )}
      {(profile.coreSkills.length > 0 || profile.skillGroups.length > 0) && (
        <Section title="Skills">
          {profile.coreSkills.length > 0 && <Chips items={profile.coreSkills} />}
          {profile.skillGroups.length > 0 && (
            <dl className="mt-4 grid gap-2 text-secondary sm:grid-cols-[8rem_1fr]">
              {profile.skillGroups.map(({ group, skills }) => (
                <div key={group} className="contents">
                  <dt className="text-muted capitalize">{group.replaceAll("_", " ")}</dt>
                  <dd>{skills.join(", ")}</dd>
                </div>
              ))}
            </dl>
          )}
        </Section>
      )}
      {profile.experiences.length > 0 && (
        <Section title="Experience">
          <ol className="space-y-4">
            {profile.experiences.map((experience, index) => (
              <li key={index}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <p className="font-medium">
                    {experience.title || "Role"}
                    {experience.company && <span className="text-muted"> · {experience.company}</span>}
                  </p>
                  <p className="text-caption text-muted">{dateRange(experience)}</p>
                </div>
                {experience.highlights.length > 0 && (
                  <div className="mt-1">
                    <Bullets items={experience.highlights} />
                  </div>
                )}
                {experience.techStack.length > 0 && (
                  <p className="mt-1 text-caption text-muted">{experience.techStack.join(" · ")}</p>
                )}
              </li>
            ))}
          </ol>
        </Section>
      )}
      {profile.projects.length > 0 && (
        <Section title="Projects">
          <ul className="space-y-3 text-secondary">
            {profile.projects.map((project, index) => (
              <li key={index}>
                <p className="font-medium">
                  {project.name}
                  {project.role && <span className="text-muted"> · {project.role}</span>}
                </p>
                {project.summary && <p className="text-muted">{project.summary}</p>}
                {project.impact.length > 0 && <Bullets items={project.impact} />}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {profile.education.length > 0 && (
        <Section title="Education">
          <Bullets items={profile.education} />
        </Section>
      )}
      {profile.certifications.length > 0 && (
        <Section title="Certifications">
          <Bullets items={profile.certifications} />
        </Section>
      )}
      {profile.languages.length > 0 && (
        <Section title="Languages">
          <Chips items={profile.languages} />
        </Section>
      )}
      {(profile.targetRoles.length > 0 ||
        profile.preferredLocations.length > 0 ||
        profile.workAuthorization) && (
        <Section title="Looking for">
          <dl className="grid gap-2 text-secondary sm:grid-cols-[8rem_1fr]">
            {profile.targetRoles.length > 0 && (
              <>
                <dt className="text-muted">Roles</dt>
                <dd>{profile.targetRoles.join(", ")}</dd>
              </>
            )}
            {profile.preferredLocations.length > 0 && (
              <>
                <dt className="text-muted">Locations</dt>
                <dd>{profile.preferredLocations.join(", ")}</dd>
              </>
            )}
            {profile.workAuthorization && (
              <>
                <dt className="text-muted">Work authorization</dt>
                <dd>{profile.workAuthorization}</dd>
              </>
            )}
          </dl>
        </Section>
      )}
    </Card>
  );
}
