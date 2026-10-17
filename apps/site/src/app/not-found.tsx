import { ButtonLink, Container } from "@/components/primitives";

export default function NotFound() {
  return (
    <Container className="flex min-h-[70vh] flex-col items-start justify-center pt-28">
      <p className="font-mono text-xs text-accent">404</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Page not found</h1>
      <p className="mt-3 text-muted">This page does not exist.</p>
      <ButtonLink href="/" variant="primary" className="mt-8">
        Back to home
      </ButtonLink>
    </Container>
  );
}
