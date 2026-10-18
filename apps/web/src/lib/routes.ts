// The console's routes. Anything else is the 404 page, which is prerendered at
// "/_not-found": treating every unknown path alike keeps server and browser renders equal.
const ROUTES = [
  /^\/$/,
  /^\/(experiments|applications|services|reports|settings|help|how-it-works|support|about)$/,
  /^\/applications\/[^/]+$/,
  /^\/applications\/imports\/[^/]+$/,
  /^\/experiments\/[^/]+$/,
  /^\/reports\/[^/]+$/,
  /^\/services\/[^/]+\/[^/]+\/[^/]+$/,
];

export function isKnownRoute(pathname: string): boolean {
  return ROUTES.some((route) => route.test(pathname));
}
