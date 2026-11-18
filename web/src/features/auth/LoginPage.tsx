import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";

import { client, unwrap } from "@/api/client";
import { describeError } from "@/api/errors";
import { keys, useConfig, useSession } from "@/api/queries";
import { Button, ErrorNote, Field, Input } from "@/components/ui";

/** Only allow in-app redirects (no open redirect through ?next=). */
function safeNext(next: string | null): string {
  return next?.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function LoginPage() {
  const session = useSession();
  const config = useConfig();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const submit = useMutation({
    mutationFn: () =>
      unwrap(
        mode === "sign-in"
          ? client.POST("/api/v1/session", { body: { username, password } })
          : client.POST("/api/v1/account", { body: { username, password } }),
      ),
    onSuccess: (data) => {
      queryClient.clear();
      queryClient.setQueryData(keys.session, data);
      void navigate(safeNext(params.get("next")), { replace: true });
    },
  });

  if (session.data?.user) return <Navigate to={safeNext(params.get("next"))} replace />;

  const signingUp = mode === "sign-up";
  const error = submit.error ? describeError(submit.error) : null;

  return (
    <main className="flex min-h-dvh items-center justify-center px-5 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-10">
          <h1 className="font-display text-title tracking-wide uppercase md:text-[2.25rem]">GivemeaChance</h1>
          <p className="mt-3 text-subheading text-muted">
            Find the right jobs and apply with tailored documents.
          </p>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit.mutate();
          }}
          className="glass hud cut-tr flex flex-col gap-5 rounded-card p-6"
        >
          <h2 className="text-heading font-semibold">{signingUp ? "Create your account" : "Sign in"}</h2>
          <Field
            label="Username"
            hint={signingUp ? "3–32 letters, digits, dots, dashes or underscores" : undefined}
          >
            {(id, hint) => (
              <Input
                id={id}
                aria-describedby={hint}
                autoComplete="username"
                required
                minLength={signingUp ? 3 : undefined}
                maxLength={signingUp ? 32 : 64}
                pattern={signingUp ? "[A-Za-z0-9_.\\-]+" : undefined}
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            )}
          </Field>
          <Field label="Password" hint={signingUp ? "At least 8 characters" : undefined}>
            {(id, hint) => (
              <Input
                id={id}
                aria-describedby={hint}
                type="password"
                autoComplete={signingUp ? "new-password" : "current-password"}
                required
                minLength={signingUp ? 8 : undefined}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            )}
          </Field>
          {error && <ErrorNote message={error.message} reference={null} />}
          <Button type="submit" variant="primary" size="lg" busy={submit.isPending} className="w-full">
            {signingUp ? "Create account" : "Sign in"}
          </Button>
        </form>
        {config.data?.registration_open && (
          <p className="mt-6 text-secondary text-muted">
            {signingUp ? "Already have an account?" : "New here?"}{" "}
            <button
              type="button"
              className="inline-flex min-h-11 items-center font-medium text-accent hover:underline"
              onClick={() => {
                setMode(signingUp ? "sign-in" : "sign-up");
                submit.reset();
              }}
            >
              {signingUp ? "Sign in" : "Create an account"}
            </button>
          </p>
        )}
      </div>
    </main>
  );
}
