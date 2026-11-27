// Delivery's existing transport uses root-relative JSON URLs. Browser
// navigations to the same URLs must still receive the React document.
export const deliveryPath = "^/(me/(?:exams|preferences)|exams/[^/]+/attempts|attempts/[^/]+(?:/items/[0-9]+|/submit)?)$";

export function vercelRoutes(origin) {
  return [
    { src: "^/api/(.*)$", dest: origin + "/api/$1" },
    { src: deliveryPath, has: [{ type: "header", key: "accept", value: "application/json" }], dest: origin + "/api/$1" },
    { handle: "filesystem" },
    { src: "^/(?:|login|admin/accounts|verify|examiner/.*|me/.*|attempts/[^/]+)/?$", dest: "/index.html" },
  ];
}
