// OutPOSt CMS public runtime v0.2.3. CMS_DB is optional and fail-open to static assets.
const CMS_PUBLIC_BUILD = "OUTPOST-CMS-PUBLIC-0.2.3";
const RESERVED = new Set(["admin","api","login","logout","cabinet","assets","downloads","cdn-cgi","robots.txt","sitemap.xml","favicon.ico","favicon.png","favicon-48.png","apple-touch-icon.png","404"]);
const CANONICAL_PUBLIC_ORIGIN = "https://outpost.com.ua";
const CANONICAL_PUBLIC_HOSTS = new Set(["outpost.com.ua","www.outpost.com.ua"]);
function isCanonicalPublicHost(url){return CANONICAL_PUBLIC_HOSTS.has(String(url?.hostname||"").toLowerCase());}
function safeCanonical(value,path){const fallback=new URL(path,CANONICAL_PUBLIC_ORIGIN).toString();const x=String(value||"").trim();if(!x)return fallback;try{const url=new URL(x);if(url.protocol!=="https:"||!isCanonicalPublicHost(url)||url.username||url.password||url.search||url.hash)return fallback;return CANONICAL_PUBLIC_ORIGIN+(url.pathname||"/");}catch{return fallback;}}

function cmsSlugFromPath(pathname) {
  if (pathname === "/") return "home";
  const value=pathname.replace(/^\/+|\/+$/g,"").toLowerCase();
  const parts=value.split("/");
  if(!value||parts.length>4||RESERVED.has(parts[0])||!parts.every((x)=>/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(x))) return null;
  return value;
}
function esc(value){return String(value??"").replace(/[&<>"']/g,(ch)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));}
function paragraphs(text){return String(text||"").split(/\n\s*\n/).filter(Boolean).map((p)=>`<p>${esc(p).replace(/\n/g,"<br>")}</p>`).join("");}
function safeHref(value){const x=String(value||"").trim();const localPath=x.startsWith("/")&&!x.startsWith("//");if(localPath||x.startsWith("#")||/^mailto:/i.test(x)||/^tel:/i.test(x))return x;if(/^https:\/\//i.test(x)){try{const url=new URL(x);if(isCanonicalPublicHost(url))return `${url.pathname||"/"}${url.search}${url.hash}`;return x;}catch{return "#";}}return "#";}
function safeImage(value){const x=String(value||"").trim();const localPath=x.startsWith("/")&&!x.startsWith("//");if(localPath)return x;if(/^https:\/\//i.test(x)){try{const url=new URL(x);if(isCanonicalPublicHost(url))return `${url.pathname||"/"}${url.search}${url.hash}`;return x;}catch{return "";}}return "";}
function parse(value,fallback){try{return JSON.parse(value||"");}catch{return fallback;}}

function imageHtml(item,cls="cms-card-image"){
  const src=safeImage(item?.imageUrl); if(!src)return "";
  const img=`<img class="${cls}" src="${esc(src)}" alt="${esc(item?.imageAlt||"")}" loading="lazy" decoding="async">`;
  return item?.href?`<a href="${esc(safeHref(item.href))}">${img}</a>`:img;
}
function cardsBlock(block,kind){const items=Array.isArray(block.items)?block.items:[];return `<section class="cms-section"><div class="cms-wrap">${block.heading?`<h2>${esc(block.heading)}</h2>`:""}${block.intro?`<p class="cms-intro">${esc(block.intro)}</p>`:""}<div class="cms-grid cms-grid-${esc(kind)}">${items.map((x)=>`<article class="cms-card">${imageHtml(x)}<h3>${esc(x.title)}</h3>${x.text?`<p>${esc(x.text)}</p>`:""}${x.href?`<a class="cms-card-link" href="${esc(safeHref(x.href))}">Дізнатися більше →</a>`:""}</article>`).join("")}</div></div></section>`;}
function renderBlock(block){
  if(block?.type==="hero"){const img=safeImage(block.imageUrl);return `<section class="cms-hero"><div class="cms-wrap cms-hero-grid"><div class="cms-hero-copy">${block.eyebrow?`<div class="cms-eyebrow">${esc(block.eyebrow)}</div>`:""}<h1>${esc(block.heading)}</h1>${block.lead?`<p>${esc(block.lead)}</p>`:""}<div class="cms-actions">${block.primaryLabel?`<a class="cms-btn cms-btn-primary" href="${esc(safeHref(block.primaryHref))}">${esc(block.primaryLabel)}</a>`:""}${block.secondaryLabel?`<a class="cms-btn" href="${esc(safeHref(block.secondaryHref))}">${esc(block.secondaryLabel)}</a>`:""}</div></div>${img?`<img class="cms-hero-image" src="${esc(img)}" alt="${esc(block.imageAlt||"")}" decoding="async">`:""}</div></section>`;}
  if(block?.type==="text")return `<section class="cms-section"><div class="cms-wrap cms-prose">${block.heading?`<h2>${esc(block.heading)}</h2>`:""}${paragraphs(block.body)}</div></section>`;
  if(block?.type==="image")return `<section class="cms-section"><div class="cms-wrap cms-image-block">${block.heading?`<h2>${esc(block.heading)}</h2>`:""}<figure>${imageHtml(block,"cms-image")}${block.caption?`<figcaption>${esc(block.caption)}</figcaption>`:""}</figure></div></section>`;
  if(["features","cards","columns"].includes(block?.type))return cardsBlock(block,block.type);
  if(block?.type==="faq")return `<section class="cms-section"><div class="cms-wrap cms-faq">${block.heading?`<h2>${esc(block.heading)}</h2>`:""}${(block.items||[]).map((x)=>`<details><summary>${esc(x.question)}</summary>${paragraphs(x.answer)}</details>`).join("")}</div></section>`;
  if(block?.type==="pricing")return `<section class="cms-section"><div class="cms-wrap">${block.heading?`<h2>${esc(block.heading)}</h2>`:""}${block.intro?`<p class="cms-intro">${esc(block.intro)}</p>`:""}<div class="cms-grid cms-pricing">${(block.items||[]).map((x)=>`<article class="cms-card cms-price"><h3>${esc(x.name)}</h3><strong>${esc(x.price)}</strong>${x.description?`<p>${esc(x.description)}</p>`:""}<ul>${(x.features||[]).map((f)=>`<li>${esc(f)}</li>`).join("")}</ul>${x.buttonLabel?`<a class="cms-btn cms-btn-primary" href="${esc(safeHref(x.buttonHref))}">${esc(x.buttonLabel)}</a>`:""}</article>`).join("")}</div></div></section>`;
  if(block?.type==="cta")return `<section class="cms-section"><div class="cms-wrap"><div class="cms-cta"><div><h2>${esc(block.heading)}</h2>${block.text?`<p>${esc(block.text)}</p>`:""}</div><a class="cms-btn cms-btn-primary" href="${esc(safeHref(block.buttonHref))}">${esc(block.buttonLabel)}</a></div></div></section>`;
  return "";
}
function faqJsonLd(blocks){const items=blocks.filter((b)=>b?.type==="faq").flatMap((b)=>Array.isArray(b.items)?b.items:[]).filter((x)=>x?.question&&x?.answer);if(!items.length)return"";const json=JSON.stringify({"@context":"https://schema.org","@type":"FAQPage",mainEntity:items.map((x)=>({"@type":"Question",name:String(x.question),acceptedAnswer:{"@type":"Answer",text:String(x.answer)}}))}).replace(/</g,"\\u003c");return `<script type="application/ld+json">${json}</script>`;}
function menuHtml(items){return(items||[]).map((x)=>`<a href="${esc(safeHref(x.href))}">${esc(x.label)}</a>`).join("");}
function settingsMap(rows){const out={};for(const row of rows||[])out[row.setting_key]=parse(row.value_json,{});return out;}

function renderCmsHtml(row,origin,menus,settings){
  const blocks=parse(row.content_json,[]); const path=row.slug==="home"?"/":`/${row.slug}`;
  const identity=settings.site_identity||{}; const seoDefaults=settings.seo_defaults||{};
  const canonical=safeCanonical(row.canonical_url,path); const seoTitle=row.seo_title||`${row.title}${seoDefaults.titleSuffix||""}`; const description=row.seo_description||seoDefaults.description||"OutPOSt — програма для керування магазином.";
  const primary=menus.primary||[{label:"Можливості",href:"/features"},{label:"Завантажити",href:"/download"}]; const footer=menus.footer||[];
  return `<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="${esc(description)}"><meta name="robots" content="${esc(row.robots||"index,follow")}"><meta name="author" content="Сапожніков Роман"><meta name="theme-color" content="#102330"><link rel="canonical" href="${esc(canonical)}"><meta property="og:type" content="website"><meta property="og:locale" content="uk_UA"><meta property="og:site_name" content="${esc(identity.name||"OutPOSt")}"><meta property="og:title" content="${esc(seoTitle)}"><meta property="og:description" content="${esc(description)}"><meta property="og:url" content="${esc(canonical)}"><title>${esc(seoTitle)}</title><link rel="icon" type="image/png" sizes="192x192" href="/favicon.png"><link rel="icon" type="image/png" sizes="48x48" href="/favicon-48.png"><link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png"><link rel="stylesheet" href="/assets/outpost-cms-v020.css">${faqJsonLd(blocks)}</head><body data-cms-build="${CMS_PUBLIC_BUILD}"><header class="cms-site-head"><div class="cms-wrap cms-nav"><a class="cms-brand" href="/"><img src="/assets/outpost-logo.png" alt="" width="40" height="40"><span>${esc(identity.name||"OutPOSt")}</span></a><nav class="cms-links" aria-label="Головна навігація">${menuHtml(primary)}</nav></div></header><main>${blocks.map(renderBlock).join("")||`<section class="cms-section"><div class="cms-wrap cms-prose"><h1>${esc(row.title)}</h1><p>Сторінка готується.</p></div></section>`}</main><footer class="cms-footer"><div class="cms-wrap cms-footer-grid"><div><strong>${esc(identity.name||"OutPOSt")}</strong><small>${esc(identity.tagline||"Програма для щоденної роботи магазину")}</small></div><div>${menuHtml(footer)}</div></div></footer></body></html>`;
}

export async function cmsPageResponse(request,env){
  if(!env.CMS_DB||!["GET","HEAD"].includes(request.method))return null; const url=new URL(request.url); const slug=cmsSlugFromPath(url.pathname);if(!slug)return null;
  const row=await env.CMS_DB.prepare(`SELECT slug,title,seo_title,seo_description,canonical_url,robots,content_json,updated_at,published_at FROM cms_pages WHERE slug=?1 AND status='published' LIMIT 1`).bind(slug).first();if(!row)return null;
  const [menuRows,settingRows]=await Promise.all([env.CMS_DB.prepare(`SELECT menu_key,items_json FROM cms_menus`).all(),env.CMS_DB.prepare(`SELECT setting_key,value_json FROM cms_site_settings`).all()]);
  const menus={};for(const item of menuRows.results||[])menus[item.menu_key]=parse(item.items_json,[]);
  const canonicalHost=isCanonicalPublicHost(url);
  const renderedRow=canonicalHost?row:{...row,robots:"noindex,nofollow"};
  const html=renderCmsHtml(renderedRow,url.origin,menus,settingsMap(settingRows.results));
  const headers={"Content-Type":"text/html; charset=utf-8","Cache-Control":"public, max-age=60, s-maxage=120","Content-Security-Policy":"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' https://cabinet.outpost.com.ua; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'","X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"strict-origin-when-cross-origin","Permissions-Policy":"camera=(), microphone=(), geolocation=(), payment=(), usb=()","X-CMS-Build":CMS_PUBLIC_BUILD};
  if(!canonicalHost)headers["X-Robots-Tag"]="noindex, nofollow";
  return new Response(request.method==="HEAD"?null:html,{status:200,headers});
}

export async function cmsRedirectResponse(request,env){if(!env.CMS_DB||!["GET","HEAD"].includes(request.method))return null;const url=new URL(request.url);if(RESERVED.has(url.pathname.split("/")[1]))return null;const row=await env.CMS_DB.prepare(`SELECT target_url,http_status FROM cms_redirects WHERE source_path=?1 AND active=1 LIMIT 1`).bind(url.pathname).first();if(!row)return null;const target=safeHref(row.target_url);if(target==="#")return null;return Response.redirect(target.startsWith("/")?new URL(target,url.origin).toString():target,Number(row.http_status||301));}
function xmlEscape(value){return String(value??"").replace(/[&<>"']/g,(ch)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"}[ch]));}
export async function cmsSitemapResponse(request,env,assetsResponse){if(!env.CMS_DB||request.method!=="GET"||!assetsResponse||assetsResponse.status!==200)return null;const requestUrl=new URL(request.url);if(requestUrl.pathname!=="/sitemap.xml"||!isCanonicalPublicHost(requestUrl))return null;const text=await assetsResponse.text();const rows=await env.CMS_DB.prepare(`SELECT slug,updated_at FROM cms_pages WHERE status='published' ORDER BY slug`).all();const origin=requestUrl.origin,add=[];for(const row of rows.results||[]){const loc=new URL(row.slug==="home"?"/":`/${row.slug}`,origin).toString();if(text.includes(`<loc>${loc}</loc>`))continue;const d=String(row.updated_at||"").slice(0,10);add.push(`<url><loc>${xmlEscape(loc)}</loc>${/^\d{4}-\d{2}-\d{2}$/.test(d)?`<lastmod>${d}</lastmod>`:""}</url>`);}const merged=add.length?text.replace(/<\/urlset>\s*$/i,`${add.join("\n")}\n</urlset>`):text;const headers=new Headers(assetsResponse.headers);headers.set("Content-Type","application/xml; charset=utf-8");headers.set("Cache-Control","public, max-age=300");return new Response(merged,{status:200,headers});}
