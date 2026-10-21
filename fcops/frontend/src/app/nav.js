// Sidebar, grouped by purpose (WP10). `show` decides per item from /me
// permissions; a group with no visible items is hidden. UI hiding is a
// convenience only: every endpoint enforces scope again.
const fcs = (p) => p.can_view_fcs

export const NAV = [
  { section: 'Work', items: [
    { to: '/', label: 'Home', icon: 'home', end: true },
    { to: '/queue', label: 'My queue', icon: 'inbox' },
    { to: '/issues', label: 'Issues', icon: 'alert' },
    { to: '/tasks', label: 'Tasks', icon: 'tasks' },
    { to: '/releases', label: 'Releases', icon: 'upload' },
  ] },
  { section: 'Hardware', items: [
    { to: '/fcs', label: 'Flight controllers', icon: 'chip', show: fcs },
    { to: '/param-compare', label: 'Test & evidence', icon: 'compare', show: fcs },
    { to: '/customers', label: 'Customers', icon: 'list', show: fcs },
    { to: '/firmware/builds', label: 'Firmware', icon: 'cpu', show: (p) => fcs(p) && p.can_manage_firmware },
  ] },
  { section: 'Knowledge', items: [
    { to: '/known-issues', label: 'Known issues', icon: 'book' },
    { to: '/search', label: 'Search', icon: 'search' },
    { to: '/audit', label: 'Activity log', icon: 'history' },
  ] },
  { section: 'Admin', items: [
    { to: '/manager/test-configuration', label: 'Test configuration', icon: 'sliders',
      show: (p) => p.can_configure_tests },
    { to: '/manager/fc-models', label: 'FC models', icon: 'layers', show: (p) => p.can_manage_fc_models },
    { to: '/admin', label: 'Accounts', icon: 'shield', show: (p) => p.is_admin },
  ] },
]

export const visibleNav = (permissions = {}) => NAV
  .map((g) => ({ ...g, items: g.items.filter((n) => !n.show || n.show(permissions)) }))
  .filter((g) => g.items.length)
