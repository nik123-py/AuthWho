import { Link } from "react-router-dom";
import { CollectionNotice } from "../components/CollectionNotice";
import { PageHeader } from "../components/PageHeader";
import { useSession } from "../session/SessionProvider";

/** The public privacy page. Reachable without signing in, from every page footer. */
export function CollectPage() {
  const { session } = useSession();
  const signedIn = session.status === "signed_in";

  return (
    <div className="max-w-4xl">
      <PageHeader title="What we collect">
        <p>
          This app uses AuthWho to check, while you work, that the person using an account is still the person
          who signed in. It does this from the rhythm of typing and pointer movement, never from what is typed.
          This page lists exactly which signals are captured and which are not.
        </p>
      </PageHeader>

      <CollectionNotice collectedTitle="Collected" neverTitle="Never collected" />

      <section className="mt-10 max-w-prose space-y-3 text-sm text-ink">
        <h2 className="text-lg font-semibold">Your choices</h2>
        <p>
          You can opt out of typing rhythm, pointer movement or page interaction, separately or all together.
          An opted-out channel is never captured, and opting out never stops you from using the app.
        </p>
        <p>
          You can withdraw consent at any time. Withdrawing deletes your behavioural profile, stored feature
          vectors and any volunteer research data, and capture stops at once. Raw events already held in memory
          expire within 24 hours.
        </p>
        <p>
          {signedIn ? (
            <>
              Change your choices or withdraw consent in{" "}
              <Link to="/settings" className="font-medium text-accent underline">
                Settings
              </Link>
              .
            </>
          ) : (
            <>
              After you{" "}
              <Link to="/login" className="font-medium text-accent underline">
                sign in
              </Link>
              , you are asked for consent before anything is captured.
            </>
          )}
        </p>
      </section>
    </div>
  );
}
