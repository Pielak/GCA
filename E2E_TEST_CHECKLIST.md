# GCA E2E Test Checklist v0.1.0

Complete this checklist before marking as production-ready.

## Environment Setup
- [ ] Docker Compose running all 4 services
- [ ] Backend health: curl http://localhost:8000/health
- [ ] Database initialized and accessible
- [ ] Redis running and responding

## Authentication
- [ ] Login page loads (http://localhost:5173)
- [ ] Login with admin credentials works
- [ ] Invalid credentials shows error
- [ ] Logout clears token and redirects
- [ ] Protected routes redirect to login when no token

## Dashboard
- [ ] Dashboard page loads
- [ ] Shows metrics (user count, tickets, alerts)
- [ ] All numbers are >0 or properly labeled

## User Management
- [ ] Users page loads with user list
- [ ] Pagination works (if >20 users)
- [ ] Lock user button works
- [ ] Unlock user button works
- [ ] Reset password button sends email
- [ ] Filter works (active/inactive)

## Projects
- [ ] Projects page loads
- [ ] Can create new project
- [ ] Can approve pending project
- [ ] Can reject project with reason
- [ ] Project status updates immediately

## Security
- [ ] Suspicious access page loads
- [ ] Shows blocked users (if any)
- [ ] Can unblock suspicious access
- [ ] Unblock updates immediately

## Support Tickets
- [ ] Tickets page loads
- [ ] Filter by status works
- [ ] Filter by severity works
- [ ] Can view ticket details
- [ ] Can add response to ticket
- [ ] Can mark ticket as resolved
- [ ] Resolved ticket shows in resolved filter

## Settings/Parametrização
- [ ] SMTP tab loads
- [ ] Can save SMTP settings
- [ ] Can send test email
- [ ] IA Providers tab loads
- [ ] Can select provider
- [ ] Can save API key
- [ ] Can test connection
- [ ] N8N tab loads

## Integrations
- [ ] Integrations page loads
- [ ] Can test webhook with valid URL
- [ ] Shows error for invalid URL
- [ ] Shows timeout message for unreachable URL

## Alerts
- [ ] Alerts page loads
- [ ] Shows alert list
- [ ] Filter by severity works
- [ ] Can acknowledge alert
- [ ] Acknowledged alert shows correct status

## UI/UX
- [ ] Dark theme applied
- [ ] All text readable (contrast OK)
- [ ] Buttons all clickable
- [ ] Forms validate (required fields)
- [ ] Error messages display
- [ ] Success toasts appear
- [ ] Loading spinners show during API calls

## Mobile Responsive
- [ ] On 375px width: sidebar collapses to hamburger
- [ ] On 768px width: table becomes card view
- [ ] Touch interactions work
- [ ] Buttons large enough to tap (>44px)

## Performance
- [ ] Initial page load <3 seconds
- [ ] API responses <500ms
- [ ] No console errors
- [ ] No memory leaks (DevTools)
- [ ] Bundle size <400KB gzipped

## Error Handling
- [ ] 401 errors show login redirect
- [ ] 404 errors show message
- [ ] Network timeout shows retry button
- [ ] Form errors highlight fields
- [ ] Error toasts disappear after 3s

## Accessibility (WCAG 2.1)
- [ ] Keyboard navigation (Tab key)
- [ ] Focus visible on all buttons
- [ ] Color not only indicator (e.g., red+X)
- [ ] Form labels associated
- [ ] Alt text on images (if any)
- [ ] Screen reader friendly (semantic HTML)

## Database
- [ ] Data persists after page reload
- [ ] Deletes don't happen unintentionally
- [ ] Concurrent requests don't corrupt data
- [ ] Pagination handles 100+ items

## Browser Compatibility
- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)

## Final Sign-Off
- [ ] All checks passed
- [ ] No blocking issues found
- [ ] Performance acceptable
- [ ] Security checklist passed
- [ ] Ready for production

---

**Tester**: _________________  
**Date**: _________________  
**Notes**: _________________
