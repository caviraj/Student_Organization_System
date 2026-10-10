import { type ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { hasMinimumRole, type Role } from '../../types/api';
import { SkeletonCard } from '../ui/Skeleton';
import { ErrorState } from '../ui/ErrorState';

export interface RequireRoleProps {
  role?: Role;
  minRole?: Role;
  children: ReactNode;
}

export function RequireRole({ role, minRole, children }: RequireRoleProps) {
  const { user, isLoading } = useAuth();
  const targetRole = role || minRole || 'member';

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto p-6 space-y-4">
        <SkeletonCard />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!hasMinimumRole(user.role, targetRole)) {
    return (
      <div className="max-w-xl mx-auto p-8">
        <ErrorState
          title="Access Restricted"
          message={`This area requires at least "${targetRole}" role privileges. Your current role is "${user.role}".`}
        />
      </div>
    );
  }

  return <>{children}</>;
}
