import { describe, it, expect } from 'vitest';
import { hasMinimumRole, ROLE_HIERARCHY } from './api';

describe('Role Hierarchy and hasMinimumRole', () => {
  it('correctly ranks roles in ascending authority order', () => {
    expect(ROLE_HIERARCHY.guest).toBeLessThan(ROLE_HIERARCHY.member);
    expect(ROLE_HIERARCHY.member).toBeLessThan(ROLE_HIERARCHY.volunteer);
    expect(ROLE_HIERARCHY.volunteer).toBeLessThan(ROLE_HIERARCHY.organizer);
    expect(ROLE_HIERARCHY.organizer).toBeLessThan(ROLE_HIERARCHY.treasurer);
    expect(ROLE_HIERARCHY.treasurer).toBeLessThan(ROLE_HIERARCHY.admin);
  });

  it('allows access when user role equals required role', () => {
    expect(hasMinimumRole('member', 'member')).toBe(true);
    expect(hasMinimumRole('admin', 'admin')).toBe(true);
    expect(hasMinimumRole('guest', 'guest')).toBe(true);
  });

  it('allows access when user role exceeds required role', () => {
    expect(hasMinimumRole('admin', 'member')).toBe(true);
    expect(hasMinimumRole('organizer', 'volunteer')).toBe(true);
    expect(hasMinimumRole('treasurer', 'guest')).toBe(true);
  });

  it('denies access when user role is below required role', () => {
    expect(hasMinimumRole('guest', 'member')).toBe(false);
    expect(hasMinimumRole('member', 'volunteer')).toBe(false);
    expect(hasMinimumRole('volunteer', 'organizer')).toBe(false);
    expect(hasMinimumRole('organizer', 'admin')).toBe(false);
  });
});
