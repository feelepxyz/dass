const CANONICAL_HOST = "feelep.xyz";
const LEGACY_HOSTS = new Set([
  "canaibuildatoiletyet.com",
  "www.canaibuildatoiletyet.com",
]);
const SITE_PREFIX = "/dass";

function canonicalPath(pathname) {
  return pathname === "/" ? `${SITE_PREFIX}/` : `${SITE_PREFIX}${pathname}`;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (LEGACY_HOSTS.has(url.hostname)) {
      const target = new URL(`https://${CANONICAL_HOST}${canonicalPath(url.pathname)}`);
      target.search = url.search;
      return Response.redirect(target.toString(), 301);
    }

    if (url.hostname === CANONICAL_HOST && url.pathname === SITE_PREFIX) {
      url.pathname = `${SITE_PREFIX}/`;
      return Response.redirect(url.toString(), 301);
    }

    if (url.hostname === CANONICAL_HOST && url.pathname === `${SITE_PREFIX}/`) {
      const indexUrl = new URL(url);
      indexUrl.pathname = `${SITE_PREFIX}/index.html`;
      return env.ASSETS.fetch(new Request(indexUrl, request));
    }

    return env.ASSETS.fetch(request);
  },
};
