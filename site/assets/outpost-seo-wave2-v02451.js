// OUTPOST-SEO-WAVE2-0.24.5.1
(()=>{"use strict";
  const nav=document.querySelector("[data-nav]")||document.getElementById("site-nav");
  const toggle=document.querySelector("[data-nav-toggle]");
  if(nav&&toggle&&!toggle.dataset.seoWave1Bound){
    toggle.dataset.seoWave1Bound="1";
    toggle.addEventListener("click",()=>{
      const open=!nav.classList.contains("outpost-nav-open");
      nav.classList.toggle("outpost-nav-open",open);
      toggle.setAttribute("aria-expanded",String(open));
      document.documentElement.classList.toggle("outpost-nav-lock",open)
    });
    nav.addEventListener("click",e=>{
      if(e.target.closest("a")&&nav.classList.contains("outpost-nav-open")){
        nav.classList.remove("outpost-nav-open");toggle.setAttribute("aria-expanded","false");
        document.documentElement.classList.remove("outpost-nav-lock")
      }
    })
  }
  const more=document.querySelector("[data-nav-more]"),moreToggle=document.querySelector("[data-nav-more-toggle]");
  if(more&&moreToggle){
    const close=()=>{more.classList.remove("is-open");moreToggle.setAttribute("aria-expanded","false")};
    moreToggle.addEventListener("click",e=>{e.stopPropagation();const open=!more.classList.contains("is-open");more.classList.toggle("is-open",open);moreToggle.setAttribute("aria-expanded",String(open))});
    document.addEventListener("click",e=>{if(!more.contains(e.target))close()});
    document.addEventListener("keydown",e=>{if(e.key==="Escape"){close();moreToggle.focus()}})
  }
})();