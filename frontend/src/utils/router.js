export function openRouteInNewTab(router, location) {
  if (!router || !location) return
  const target = router.resolve(location)
  if (!target?.href) return
  window.open(target.href, '_blank', 'noopener,noreferrer')
}
