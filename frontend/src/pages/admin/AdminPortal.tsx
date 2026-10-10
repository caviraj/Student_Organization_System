import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminPortalApi, type CreateDepartmentEventInput, type CreateCompanyProductInput } from '../../api/adminPortal';
import { useToast } from '../../components/ui/Toast';
import {
  GraduationCap,
  Calendar,
  Users,
  Mail,
  Plus,
  Package,
  ShoppingBag,
  Database,
  Building2,
  CheckCircle2,
  Ticket,
  Copy,
  Clock,
  MapPin,
  Trash2,
} from 'lucide-react';

const DEPARTMENTS = [
  { code: 'AIDS', name: 'Artificial Intelligence & Data Science', icon: '🤖' },
  { code: 'CSE', name: 'Computer Science & Engineering', icon: '💻' },
  { code: 'IT', name: 'Information Technology', icon: '🌐' },
  { code: 'CIVIL', name: 'Civil Engineering', icon: '🏗️' },
  { code: 'MECH', name: 'Mechanical Engineering', icon: '⚙️' },
  { code: 'AIML', name: 'AI & Machine Learning', icon: '🧠' },
  { code: 'BIO TECH', name: 'Biotechnology', icon: '🧬' },
  { code: 'ECE', name: 'Electronics & Communication', icon: '📡' },
  { code: 'EEE', name: 'Electrical & Electronics', icon: '⚡' },
];

export function AdminPortal() {
  const queryClient = useQueryClient();
  const { success: showToastSuccess, error: showToastError } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialTab = searchParams.get('tab') === 'products' ? 'products' : 'departments';
  const [activeTab, setActiveTab] = useState<'departments' | 'products'>(initialTab);
  const [selectedDept, setSelectedDept] = useState<string>('AIDS');
  const [isEventModalOpen, setIsEventModalOpen] = useState(false);
  const [copiedEmail, setCopiedEmail] = useState<string | null>(null);

  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam === 'products') {
      setActiveTab('products');
    } else if (tabParam === 'departments') {
      setActiveTab('departments');
    }
  }, [searchParams]);

  const handleTabChange = (tab: 'departments' | 'products') => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  // New Event Form State
  const [eventForm, setEventForm] = useState<Omit<CreateDepartmentEventInput, 'department'>>({
    title: '',
    description: '',
    venue: '',
    starts_at: new Date(Date.now() + 86400000).toISOString().slice(0, 16),
    ends_at: new Date(Date.now() + 86400000 + 7200000).toISOString().slice(0, 16),
    capacity: 60,
    price_inr: 0,
    banner_url: '',
  });

  // New Product Form State
  const [productForm, setProductForm] = useState<CreateCompanyProductInput>({
    name: '',
    company_name: '',
    price_inr: 499,
    stock: 50,
    image_url: '',
    description: '',
  });

  // Fetch departments stats
  const { data: deptData } = useQuery({
    queryKey: ['adminPortalDepartments'],
    queryFn: adminPortalApi.getDepartments,
    refetchInterval: 15000,
  });

  // Fetch events for selected department
  const {
    data: eventsData,
    isLoading: isEventsLoading,
  } = useQuery({
    queryKey: ['adminPortalDepartmentEvents', selectedDept],
    queryFn: () => adminPortalApi.getDepartmentEvents(selectedDept),
    enabled: !!selectedDept,
  });

  // Fetch company products
  const {
    data: productsData,
    isLoading: isProductsLoading,
  } = useQuery({
    queryKey: ['adminPortalProducts'],
    queryFn: adminPortalApi.getCompanyProducts,
  });

  // Create Event Mutation
  const createEventMutation = useMutation({
    mutationFn: (data: CreateDepartmentEventInput) => adminPortalApi.createDepartmentEvent(data),
    onSuccess: (res) => {
      showToastSuccess(res.message || 'Event created successfully for department!');
      setIsEventModalOpen(false);
      setEventForm({
        title: '',
        description: '',
        venue: '',
        starts_at: new Date(Date.now() + 86400000).toISOString().slice(0, 16),
        ends_at: new Date(Date.now() + 86400000 + 7200000).toISOString().slice(0, 16),
        capacity: 60,
        price_inr: 0,
        banner_url: '',
      });
      queryClient.invalidateQueries({ queryKey: ['adminPortalDepartmentEvents', selectedDept] });
      queryClient.invalidateQueries({ queryKey: ['adminPortalDepartments'] });
    },
    onError: (err: any) => {
      showToastError(err.message || 'Failed to create department event.');
    },
  });

  // Create Product Mutation
  const createProductMutation = useMutation({
    mutationFn: (data: CreateCompanyProductInput) => adminPortalApi.createCompanyProduct(data),
    onSuccess: (res) => {
      showToastSuccess(res.message || 'Company product added to database successfully!');
      setProductForm({
        name: '',
        company_name: '',
        price_inr: 499,
        stock: 50,
        image_url: '',
        description: '',
      });
      queryClient.invalidateQueries({ queryKey: ['adminPortalProducts'] });
    },
    onError: (err: any) => {
      showToastError(err.message || 'Failed to add company product.');
    },
  });

  // Delete Product Mutation
  const deleteProductMutation = useMutation({
    mutationFn: (productId: string) => adminPortalApi.deleteCompanyProduct(productId),
    onSuccess: (res) => {
      showToastSuccess(res.message || 'Product removed successfully.');
      queryClient.invalidateQueries({ queryKey: ['adminPortalProducts'] });
    },
    onError: (err: any) => {
      showToastError(err.message || 'Failed to remove product.');
    },
  });

  const handleCreateEventSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!eventForm.title.trim()) {
      showToastError('Please enter event title.');
      return;
    }
    createEventMutation.mutate({
      ...eventForm,
      department: selectedDept,
    });
  };

  const handleCreateProductSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!productForm.name.trim()) {
      showToastError('Please enter product name.');
      return;
    }
    createProductMutation.mutate(productForm);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedEmail(text);
    showToastSuccess(`Copied: ${text}`);
    setTimeout(() => setCopiedEmail(null), 2500);
  };

  const copyAllEmails = (emails: string[]) => {
    if (!emails.length) return;
    const text = emails.join(', ');
    navigator.clipboard.writeText(text);
    showToastSuccess(`Copied ${emails.length} email IDs to clipboard!`);
  };

  const selectedDeptInfo = DEPARTMENTS.find((d) => d.code === selectedDept);
  const deptSummary = deptData?.departments?.find((d) => d.department === selectedDept);

  return (
    <div className="min-h-screen bg-slate-50/50 pb-20">
      {/* Top Banner / Header */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold mb-3">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <Database className="w-3.5 h-3.5" />
                Connected to Supabase PostgreSQL Database
              </div>
              <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                <GraduationCap className="w-8 h-8 text-indigo-600" />
                College Admin Portal
              </h1>
              <p className="mt-1 text-sm text-slate-600">
                Department Events, Registered Student Emails & Company Products Management
              </p>
            </div>

            {/* Portal Tab Switcher */}
            <div className="flex items-center bg-slate-100 p-1.5 rounded-2xl border border-slate-200/80 shadow-inner">
              <button
                type="button"
                onClick={() => handleTabChange('departments')}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  activeTab === 'departments'
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Building2 className="w-4 h-4" />
                Departments & Events
              </button>
              <button
                type="button"
                onClick={() => handleTabChange('products')}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                  activeTab === 'products'
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <ShoppingBag className="w-4 h-4" />
                Company Products (Student Needs)
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Container */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        {/* ===================== TAB 1: DEPARTMENTS & EVENTS ===================== */}
        {activeTab === 'departments' && (
          <div className="space-y-8">
            {/* Department Selection Bar */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                    <Building2 className="w-5 h-5 text-indigo-600" />
                    College Departments
                  </h2>
                  <p className="text-xs text-slate-500">
                    Click any department to view its events and registered student email records.
                  </p>
                </div>
                <span className="text-xs font-semibold px-2.5 py-1 bg-indigo-50 text-indigo-700 rounded-lg border border-indigo-100">
                  9 Departments Available
                </span>
              </div>

              {/* 9 Department Cards Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-9 gap-3">
                {DEPARTMENTS.map((dept) => {
                  const isSelected = selectedDept === dept.code;
                  const stats = deptData?.departments?.find((d) => d.department === dept.code);

                  return (
                    <button
                      key={dept.code}
                      type="button"
                      onClick={() => setSelectedDept(dept.code)}
                      className={`relative flex flex-col items-center justify-center p-3.5 rounded-2xl border text-center transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-indigo-600 text-white border-indigo-600 shadow-lg shadow-indigo-600/25 scale-105 z-10'
                          : 'bg-white text-slate-800 border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/40 shadow-xs'
                      }`}
                    >
                      <span className="text-2xl mb-1.5">{dept.icon}</span>
                      <span className={`font-black text-sm tracking-tight ${isSelected ? 'text-white' : 'text-slate-900'}`}>
                        {dept.code}
                      </span>
                      <span
                        className={`text-[10px] line-clamp-1 leading-tight mt-0.5 ${
                          isSelected ? 'text-indigo-100' : 'text-slate-500'
                        }`}
                        title={dept.name}
                      >
                        {dept.name}
                      </span>

                      {/* Small Counter Pill */}
                      <div
                        className={`mt-2 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          isSelected
                            ? 'bg-white/20 text-white'
                            : 'bg-slate-100 text-slate-600 border border-slate-200'
                        }`}
                      >
                        {stats?.events_count || 0} Events
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Selected Department Overview Banner */}
            <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-100">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center text-3xl font-black border border-indigo-100">
                    {selectedDeptInfo?.icon}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-md">
                        Selected Department
                      </span>
                      <span className="text-xs text-slate-400">•</span>
                      <span className="text-xs font-semibold text-slate-500">
                        {deptSummary?.registered_count || 0} Total Registrations
                      </span>
                    </div>
                    <h3 className="text-xl sm:text-2xl font-black text-slate-900">
                      {selectedDept} - {selectedDeptInfo?.name}
                    </h3>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setIsEventModalOpen(true)}
                  className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 text-white font-semibold text-sm hover:bg-indigo-700 shadow-md shadow-indigo-600/20 transition-all"
                >
                  <Plus className="w-4 h-4" />
                  Add Event for {selectedDept}
                </button>
              </div>

              {/* Department Quick Stats Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-6">
                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center">
                    <Calendar className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-slate-500">Department Events</p>
                    <p className="text-xl font-black text-slate-900">{eventsData?.total_events || 0}</p>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center">
                    <Ticket className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-slate-500">Total Registered</p>
                    <p className="text-xl font-black text-slate-900">{deptSummary?.registered_count || 0}</p>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-600 flex items-center justify-center">
                    <Users className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-slate-500">Registered Students</p>
                    <p className="text-xl font-black text-slate-900">{deptSummary?.students_count || 0}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Department Events List & Registered Students */}
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <Calendar className="w-5 h-5 text-indigo-600" />
                  Events for {selectedDept} Department
                </h3>
                <span className="text-xs text-slate-500 font-medium">
                  Showing {eventsData?.events?.length || 0} events
                </span>
              </div>

              {isEventsLoading ? (
                <div className="bg-white rounded-3xl p-12 text-center border border-slate-200">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mb-3" />
                  <p className="text-sm text-slate-500 font-medium">Loading department events from database...</p>
                </div>
              ) : eventsData?.events?.length === 0 ? (
                <div className="bg-white rounded-3xl p-12 text-center border border-dashed border-slate-300">
                  <div className="w-16 h-16 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-4">
                    <Calendar className="w-8 h-8" />
                  </div>
                  <h4 className="text-base font-bold text-slate-900">No events found for {selectedDept}</h4>
                  <p className="text-sm text-slate-500 max-w-md mx-auto mt-1 mb-6">
                    Create the first event for {selectedDept} department so students can register.
                  </p>
                  <button
                    type="button"
                    onClick={() => setIsEventModalOpen(true)}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white font-semibold text-sm hover:bg-indigo-700 shadow-sm"
                  >
                    <Plus className="w-4 h-4" />
                    Create Event for {selectedDept}
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-8">
                  {eventsData?.events?.map((event) => {
                    const capacityPercent = Math.min(
                      Math.round(((event.registered_count || 0) / (event.capacity || 1)) * 100),
                      100
                    );
                    const allEmails = (event.registered_students || []).map((s) => s.student_email);

                    return (
                      <div
                        key={event.id}
                        className="bg-white rounded-3xl border border-slate-200/90 shadow-sm overflow-hidden"
                      >
                        {/* Event Header Card */}
                        <div className="p-6 border-b border-slate-100 bg-linear-to-r from-slate-50/50 to-white">
                          <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                            <div className="space-y-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-100">
                                  {event.department} Event
                                </span>
                                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-100">
                                  {event.status.toUpperCase()}
                                </span>
                                {event.price_inr === 0 ? (
                                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-cyan-50 text-cyan-700 border border-cyan-100">
                                    FREE ENTRY
                                  </span>
                                ) : (
                                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-100">
                                    ₹{event.price_inr}
                                  </span>
                                )}
                              </div>

                              <h4 className="text-xl font-black text-slate-900 tracking-tight">{event.title}</h4>

                              {event.description && (
                                <p className="text-sm text-slate-600 line-clamp-2 max-w-3xl">
                                  {event.description}
                                </p>
                              )}

                              <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 pt-1">
                                <span className="inline-flex items-center gap-1.5 font-medium">
                                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                                  {new Date(event.starts_at).toLocaleString('en-IN', {
                                    day: 'numeric',
                                    month: 'short',
                                    year: 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit',
                                  })}
                                </span>
                                {event.venue && (
                                  <span className="inline-flex items-center gap-1.5 font-medium">
                                    <MapPin className="w-3.5 h-3.5 text-slate-400" />
                                    {event.venue}
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Registration Progress Block */}
                            <div className="lg:w-72 bg-white rounded-2xl p-4 border border-slate-200/80 shadow-xs">
                              <div className="flex items-center justify-between text-xs mb-1.5">
                                <span className="font-semibold text-slate-600">Students Registered</span>
                                <span className="font-black text-indigo-700 text-sm">
                                  {event.registered_count} / {event.capacity}
                                </span>
                              </div>
                              <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all ${
                                    capacityPercent >= 90
                                      ? 'bg-rose-500'
                                      : capacityPercent >= 60
                                      ? 'bg-amber-500'
                                      : 'bg-emerald-500'
                                  }`}
                                  style={{ width: `${capacityPercent}%` }}
                                />
                              </div>
                              <p className="text-[11px] text-slate-500 mt-2 text-right">
                                {event.capacity - event.registered_count} seats remaining
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Registered Students Details Section */}
                        <div className="p-6">
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                            <div>
                              <h5 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                                <Mail className="w-4 h-4 text-indigo-600" />
                                Registered Student Email Records ({event.registered_students?.length || 0})
                              </h5>
                              <p className="text-xs text-slate-500">
                                List of students from {selectedDept} registered for this event with verified email IDs.
                              </p>
                            </div>

                            {allEmails.length > 0 && (
                              <button
                                type="button"
                                onClick={() => copyAllEmails(allEmails)}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors self-start sm:self-auto"
                              >
                                <Copy className="w-3.5 h-3.5" />
                                Copy All Email IDs ({allEmails.length})
                              </button>
                            )}
                          </div>

                          {/* Students Table */}
                          {!event.registered_students || event.registered_students.length === 0 ? (
                            <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center bg-slate-50/50">
                              <Users className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                              <p className="text-xs font-medium text-slate-600">
                                No student registrations recorded yet for this event.
                              </p>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                When students register, their names and email IDs will automatically display here.
                              </p>
                            </div>
                          ) : (
                            <div className="overflow-x-auto rounded-2xl border border-slate-200">
                              <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                                <thead className="bg-slate-50 font-bold text-slate-600">
                                  <tr>
                                    <th className="px-4 py-3">#</th>
                                    <th className="px-4 py-3">Student Email ID (Important)</th>
                                    <th className="px-4 py-3">Student Name</th>
                                    <th className="px-4 py-3">Ticket Code</th>
                                    <th className="px-4 py-3">Status</th>
                                    <th className="px-4 py-3">Registration Date</th>
                                    <th className="px-4 py-3 text-right">Action</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 bg-white">
                                  {event.registered_students.map((student, idx) => (
                                    <tr key={student.ticket_code || idx} className="hover:bg-slate-50/70 transition-colors">
                                      <td className="px-4 py-3 font-mono text-slate-400">{idx + 1}</td>
                                      <td className="px-4 py-3">
                                        <div className="flex items-center gap-2">
                                          <Mail className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                                          <span className="font-mono font-semibold text-slate-900 bg-indigo-50/60 px-2 py-0.5 rounded text-[11px] select-all border border-indigo-100/50">
                                            {student.student_email}
                                          </span>
                                        </div>
                                      </td>
                                      <td className="px-4 py-3 font-semibold text-slate-800">
                                        {student.student_name}
                                      </td>
                                      <td className="px-4 py-3 font-mono text-slate-600">
                                        {student.ticket_code}
                                      </td>
                                      <td className="px-4 py-3">
                                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                          {student.status.toUpperCase()}
                                        </span>
                                      </td>
                                      <td className="px-4 py-3 text-slate-500">
                                        {student.registered_at
                                          ? new Date(student.registered_at).toLocaleString('en-IN', {
                                              day: 'numeric',
                                              month: 'short',
                                              hour: '2-digit',
                                              minute: '2-digit',
                                            })
                                          : 'Confirmed'}
                                      </td>
                                      <td className="px-4 py-3 text-right">
                                        <button
                                          type="button"
                                          onClick={() => copyToClipboard(student.student_email)}
                                          className="p-1 rounded hover:bg-slate-100 text-slate-500 hover:text-indigo-600 transition-colors"
                                          title="Copy email ID"
                                        >
                                          {copiedEmail === student.student_email ? (
                                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                                          ) : (
                                            <Copy className="w-3.5 h-3.5" />
                                          )}
                                        </button>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ===================== TAB 2: COMPANY PRODUCTS (STUDENT NEEDS) ===================== */}
        {activeTab === 'products' && (
          <div className="space-y-8">
            {/* Informational Guidance Alert */}
            <div className="bg-amber-50/90 border border-amber-200 rounded-3xl p-5 flex items-start gap-4">
              <div className="w-10 h-10 rounded-2xl bg-amber-500 text-white flex items-center justify-center shrink-0 shadow-sm">
                <ShoppingBag className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-amber-950">
                  Company Products for Student Needs (Optional Purchase)
                </h4>
                <p className="text-xs text-amber-900 leading-relaxed">
                  Products added here are saved to the database and will appear directly in the Student Portal.
                  <strong> Note:</strong> Purchasing is entirely optional for students—it is not compulsory. If students need the product, they can purchase it; otherwise no extra obligation is required.
                </p>
              </div>
            </div>

            {/* Add Product Form & Live Inventory Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              {/* Product Creation Card (Left side: 5 cols) */}
              <div className="lg:col-span-5 bg-white rounded-3xl p-6 border border-slate-200 shadow-sm">
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2 mb-1">
                  <Package className="w-5 h-5 text-indigo-600" />
                  Add Company Product
                </h3>
                <p className="text-xs text-slate-500 mb-6">
                  Add tools, kits, books, or devices needed by students.
                </p>

                <form onSubmit={handleCreateProductSubmit} className="space-y-4 text-xs">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Product Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Scientific Calculator FX-991CW"
                      value={productForm.name}
                      onChange={(e) => setProductForm({ ...productForm, name: e.target.value })}
                      className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs text-slate-800"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Company / Manufacturer Brand
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Casio / Cambridge / Campus Supplies"
                      value={productForm.company_name}
                      onChange={(e) => setProductForm({ ...productForm, company_name: e.target.value })}
                      className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs text-slate-800"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">
                        Price (₹ INR) <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="number"
                        min="0"
                        step="1"
                        required
                        value={productForm.price_inr}
                        onChange={(e) =>
                          setProductForm({ ...productForm, price_inr: parseFloat(e.target.value) || 0 })
                        }
                        className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs text-slate-800 font-semibold"
                      />
                    </div>

                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">
                        Available Stock <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="number"
                        min="1"
                        required
                        value={productForm.stock}
                        onChange={(e) =>
                          setProductForm({ ...productForm, stock: parseInt(e.target.value) || 0 })
                        }
                        className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs text-slate-800 font-semibold"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Image URL (Optional)
                    </label>
                    <input
                      type="url"
                      placeholder="https://images.unsplash.com/..."
                      value={productForm.image_url}
                      onChange={(e) => setProductForm({ ...productForm, image_url: e.target.value })}
                      className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs text-slate-800"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Description & Specs
                    </label>
                    <textarea
                      rows={3}
                      placeholder="Details, warranty, or requirements for students..."
                      value={productForm.description}
                      onChange={(e) => setProductForm({ ...productForm, description: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs text-slate-800"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={createProductMutation.isPending}
                    className="w-full py-3 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-md shadow-indigo-600/20 transition-all disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {createProductMutation.isPending ? (
                      <>
                        <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Saving to Database...
                      </>
                    ) : (
                      <>
                        <Plus className="w-4 h-4" />
                        Add Company Product to Database
                      </>
                    )}
                  </button>
                </form>
              </div>

              {/* Product List / Current Inventory (Right side: 7 cols) */}
              <div className="lg:col-span-7 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <ShoppingBag className="w-5 h-5 text-indigo-600" />
                    Company Products Active in Portal ({productsData?.total || 0})
                  </h3>
                  <span className="text-xs text-slate-500 font-medium">Visible to Students</span>
                </div>

                {isProductsLoading ? (
                  <div className="bg-white rounded-3xl p-12 text-center border border-slate-200">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mb-3" />
                    <p className="text-sm text-slate-500">Loading products from database...</p>
                  </div>
                ) : productsData?.products?.length === 0 ? (
                  <div className="bg-white rounded-3xl p-12 text-center border border-dashed border-slate-300">
                    <Package className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                    <h4 className="text-base font-bold text-slate-900">No company products added yet</h4>
                    <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
                      Use the form on the left to add equipment, tools, or supplies for students.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {productsData?.products?.map((prod) => (
                      <div
                        key={prod.id}
                        className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow relative group"
                      >
                        <div>
                          {prod.image_url ? (
                            <img
                              src={prod.image_url}
                              alt={prod.name}
                              className="w-full h-36 object-cover rounded-xl mb-3 bg-slate-100"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = 'none';
                              }}
                            />
                          ) : (
                            <div className="w-full h-28 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
                              <Package className="w-8 h-8" />
                            </div>
                          )}

                          <div className="flex items-center gap-2 mb-1">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-100">
                              {prod.company_name}
                            </span>
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700">
                              Stock: {prod.stock}
                            </span>
                          </div>

                          <h4 className="font-bold text-sm text-slate-900 line-clamp-1">{prod.name}</h4>
                          {prod.description && (
                            <p className="text-xs text-slate-500 line-clamp-2 mt-1">{prod.description}</p>
                          )}
                        </div>

                        <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                          <div>
                            <span className="text-xs text-slate-400">Price: </span>
                            <span className="text-base font-black text-slate-900">₹{prod.price_inr}</span>
                          </div>

                          <button
                            type="button"
                            onClick={() => {
                              if (confirm(`Remove "${prod.name}" from database?`)) {
                                deleteProductMutation.mutate(prod.id);
                              }
                            }}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                            title="Remove Product"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ===================== MODAL: CREATE DEPARTMENT EVENT ===================== */}
      {isEventModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100 mb-4">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">
                  {selectedDept} Department
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">
                  Add Event for {selectedDept}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsEventModalOpen(false)}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateEventSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  Event Title <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder={`e.g. ${selectedDept} Annual Symposium / Workshop 2026`}
                  value={eventForm.title}
                  onChange={(e) => setEventForm({ ...eventForm, title: e.target.value })}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  Venue / Location
                </label>
                <input
                  type="text"
                  placeholder="e.g. Auditorium / Lab 3 / Seminar Hall"
                  value={eventForm.venue || ''}
                  onChange={(e) => setEventForm({ ...eventForm, venue: e.target.value })}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    Start Date & Time <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="datetime-local"
                    required
                    value={eventForm.starts_at}
                    onChange={(e) => setEventForm({ ...eventForm, starts_at: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 text-xs"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    End Date & Time <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="datetime-local"
                    required
                    value={eventForm.ends_at}
                    onChange={(e) => setEventForm({ ...eventForm, ends_at: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 text-xs"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    Capacity (Seats) <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    required
                    value={eventForm.capacity}
                    onChange={(e) =>
                      setEventForm({ ...eventForm, capacity: parseInt(e.target.value) || 0 })
                    }
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 text-xs font-semibold"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    Registration Fee (₹ INR)
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    placeholder="0 for Free"
                    value={eventForm.price_inr}
                    onChange={(e) =>
                      setEventForm({ ...eventForm, price_inr: parseFloat(e.target.value) || 0 })
                    }
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 text-xs font-semibold"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  Event Description
                </label>
                <textarea
                  rows={3}
                  placeholder="Agenda, prerequisites, chief guests..."
                  value={eventForm.description}
                  onChange={(e) => setEventForm({ ...eventForm, description: e.target.value })}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 text-xs"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsEventModalOpen(false)}
                  className="px-4 py-2.5 rounded-xl border border-slate-200 text-slate-700 font-semibold hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createEventMutation.isPending}
                  className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold shadow-md shadow-indigo-600/20 transition-all disabled:opacity-50"
                >
                  {createEventMutation.isPending ? 'Publishing Event...' : `Publish ${selectedDept} Event`}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
export default AdminPortal;
