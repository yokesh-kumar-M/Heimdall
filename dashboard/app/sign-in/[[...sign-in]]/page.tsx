import { SignIn } from "@clerk/nextjs";

export default function Page() {
  return (
    <div className="flex-1 flex items-center justify-center px-6 py-16">
      <SignIn appearance={{ variables: { colorPrimary: "#7c5cff" } }} />
    </div>
  );
}
