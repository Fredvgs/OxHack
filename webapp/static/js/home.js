// Home page b-roll: the clips in .reel take turns, fading from one to the next every few seconds
// (data-seconds), each starting at its data-start and with its credit underneath. With reduced
// motion asked for, the first clip's still stays on screen and nothing plays.

const reel = document.querySelector(".reel");
const clips = [...reel.querySelectorAll("video")];
const caption = document.getElementById("broll-caption");
let current = 0;

function show(i) {
  clips.forEach((clip, k) => clip.classList.toggle("on", k === i));
  clips[i].currentTime = Number(clips[i].dataset.start ?? 0);
  clips[i].play().catch(() => {}); // a browser may refuse to autoplay; the still stays
  caption.textContent = clips[i].dataset.caption;
  // the previous clip stops once it has faded out, so only one plays at a time
  const previous = clips[(i - 1 + clips.length) % clips.length];
  setTimeout(() => previous !== clips[i] && previous.pause(), 1000);
}

if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
  clips[0].classList.add("on");
  caption.textContent = clips[0].dataset.caption;
} else {
  show(0);
  setInterval(() => {
    current = (current + 1) % clips.length;
    show(current);
  }, Number(reel.dataset.seconds) * 1000);
}
