'use strict';

const $ = selector => document.querySelector(selector);
const refreshButton = $('#refresh-signups');
const eventTitle = $('#event-title');
const feedCount = $('#feed-count');
const feedStatus = $('#feed-status');
const signupList = $('#signups');
const emptyMessage = $('#feed-empty');
const avatarHosts = new Set(['assets.reclub.co','d1upr18ac2olqz.cloudfront.net']);
const minimumRefreshInterval = 60000;
let latestFeed = null;
let requestStartedAt = 0;
let loading = false;

function safeAvatar(value) {
  if (typeof value !== 'string' || value.length > 2048) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || !avatarHosts.has(url.hostname.toLowerCase())
      || url.username || url.password || (url.port && url.port !== '443')
      || url.search || url.hash || !url.pathname.startsWith('/')) return null;
    return url.href;
  } catch {
    return null;
  }
}

function parseFeed(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || !value.event || typeof value.event !== 'object' || Array.isArray(value.event)
    || typeof value.event.title !== 'string' || !Array.isArray(value.signups)
    || !Array.isArray(value.warnings) || typeof value.fetchedAt !== 'string'
    || !Number.isFinite(Date.parse(value.fetchedAt))) {
    throw new Error('The attendee feed returned an unsupported response.');
  }
  const signups = value.signups.map(signup => {
    if (!signup || typeof signup !== 'object' || Array.isArray(signup)
      || typeof signup.slotId !== 'string' || !signup.slotId
      || signup.status !== 1 || typeof signup.name !== 'string') {
      throw new Error('The attendee feed returned an unsupported sign-up.');
    }
    return {name:signup.name,avatarUrl:safeAvatar(signup.avatarUrl)};
  });
  const warnings = value.warnings.filter(warning => typeof warning === 'string');
  const fetchedAt = Date.parse(value.fetchedAt);
  const age = Date.now() - fetchedAt;
  const stale = age > 60000;
  if (stale) {
    const time = new Date(fetchedAt).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});
    warnings.unshift(`Data was last fetched at ${time}; this list may be out of date.`);
  }
  return {title:value.event.title,warnings,signups,fetchedAt};
}

function initials(name) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words.slice(0,2).map(word => word[0]).join('') : (words[0] || '?').slice(0,2)).toUpperCase();
}

function renderFeed(feed) {
  eventTitle.textContent = feed.title;
  feedCount.textContent = `${feed.signups.length} sign-up${feed.signups.length === 1 ? '' : 's'}`;
  signupList.replaceChildren();
  for (const signup of feed.signups) {
    const item = document.createElement('li');
    item.className = 'signup-row';
    const avatar = document.createElement('span');
    avatar.className = 'signup-avatar';
    avatar.setAttribute('aria-hidden','true');
    if (signup.avatarUrl) {
      const image = document.createElement('img');
      image.src = signup.avatarUrl;
      image.alt = '';
      image.loading = 'lazy';
      image.referrerPolicy = 'no-referrer';
      image.addEventListener('error',() => {
        avatar.textContent = initials(signup.name);
        image.remove();
      },{once:true});
      avatar.append(image);
    } else {
      avatar.textContent = initials(signup.name);
    }
    const name = document.createElement('span');
    name.className = 'signup-name';
    name.textContent = signup.name;
    const status = document.createElement('span');
    status.className = 'signup-status';
    status.textContent = 'Signed up';
    item.append(avatar,name,status);
    signupList.append(item);
  }
  emptyMessage.hidden = feed.signups.length !== 0;
  if (feed.warnings.length) {
    feedStatus.textContent = feed.warnings.join(' ');
  } else {
    const time = new Date(feed.fetchedAt).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});
    feedStatus.textContent = `Last fetched at ${time}.`;
  }
  feedStatus.classList.toggle('is-warning',feed.warnings.length > 0);
}

async function refreshSignups() {
  if (loading) return;
  const remaining = minimumRefreshInterval - (Date.now() - requestStartedAt);
  if (requestStartedAt && remaining > 0) {
    feedStatus.textContent = `Please wait ${Math.ceil(remaining / 1000)} seconds before refreshing again.`;
    feedStatus.classList.add('is-warning');
    return;
  }
  loading = true;
  requestStartedAt = Date.now();
  refreshButton.disabled = true;
  refreshButton.textContent = 'Refreshing…';
  if (!latestFeed) feedCount.textContent = 'Loading sign-ups…';
  try {
    const response = await fetch('/api/attendees',{headers:{Accept:'application/json'},credentials:'omit'});
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error('The sign-up service returned an unreadable response.');
    }
    if (!response.ok) {
      throw new Error(typeof payload?.error === 'string' ? payload.error : 'Sign-ups could not be loaded.');
    }
    latestFeed = parseFeed(payload);
    renderFeed(latestFeed);
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'Sign-ups could not be loaded.';
    feedStatus.textContent = latestFeed
      ? `Could not refresh. Showing the last successfully loaded sign-ups, which may be out of date. ${detail}`
      : `${detail} No sign-up count is available while Reclub cannot be reached.`;
    feedStatus.classList.add('is-warning');
    if (!latestFeed) {
      eventTitle.textContent = 'Sign-ups unavailable';
      feedCount.textContent = 'The event could not be loaded.';
      signupList.replaceChildren();
      emptyMessage.hidden = true;
    }
  } finally {
    loading = false;
    refreshButton.disabled = false;
    refreshButton.textContent = 'Refresh sign-ups';
  }
}

refreshButton.addEventListener('click',refreshSignups);
refreshSignups();
