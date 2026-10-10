import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../context/AuthContext';
import {
  studentPortalApi,
  type StudentEventItem,
  type StudentTicketItem,
  type StudentRegisterPayload,
} from '../../api/studentPortal';
import { openRazorpayCheckout } from '../../lib/razorpay';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { useToast } from '../../components/ui/Toast';
import { formatDateTime } from '../../lib/formatDate';
import { QRCodeSVG } from 'qrcode.react';
import {
  GraduationCap,
  Building2,
  Calendar,
  Ticket,
  Mail,
  MapPin,
  CheckCircle2,
  Users,
  ShoppingBag,
  CreditCard,
  X,
  Copy,
  ShieldCheck,
} from 'lucide-react';

const DEPARTMENTS = [
  'AIDS',
  'CSE',
  'IT',
  'CIVIL',
  'MECH',
  'AIML',
  'BIO TECH',
  'ECE',
  'EEE',
];

const YEARS = ['1st Year', '2nd Year', '3rd Year', '4th Year'];
const GENDERS = ['Male', 'Female', 'Other'];

export function MemberDashboard() {
  const { user } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'events' | 'tickets'>('events');
  const [selectedDept, setSelectedDept] = useState<string>('CSE');

  // Registration Modal State
  const [selectedEvent, setSelectedEvent] = useState<StudentEventItem | null>(null);
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);

  // Form Fields as specified by User:
  // (name, department*, which year*, section*, gender*, email id*)
  const [formName, setFormName] = useState(user?.full_name || '');
  const [formDept, setFormDept] = useState(user?.department || 'CSE');
  const [formYear, setFormYear] = useState('2nd Year');
  const [formSection, setFormSection] = useState('A');
  const [formGender, setFormGender] = useState('Male');
  const [formEmail, setFormEmail] = useState(user?.email || '');

  // Related Product choice: Buy or Not Buy
  const [buyProduct, setBuyProduct] = useState<boolean>(false);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);

  const [isProcessingPayment, setIsProcessingPayment] = useState<boolean>(false);

  // Queries
  const { data: deptSummaryData } = useQuery({
    queryKey: ['studentPortal', 'departments'],
    queryFn: () => studentPortalApi.getDepartments(),
  });

  const { data: deptEventsData, isLoading: isEventsLoading } = useQuery({
    queryKey: ['studentPortal', 'departmentEvents', selectedDept],
    queryFn: () => studentPortalApi.getDepartmentEvents(selectedDept),
    enabled: !!selectedDept,
  });

  const { data: myTicketsData, isLoading: isTicketsLoading } = useQuery({
    queryKey: ['studentPortal', 'myTickets'],
    queryFn: () => studentPortalApi.getMyTickets(),
  });

  const departmentEvents = deptEventsData?.events || [];
  const myTickets = myTicketsData?.tickets || [];

  // Open Registration Modal
  const handleOpenRegister = (event: StudentEventItem) => {
    setSelectedEvent(event);
    setFormName(user?.full_name || '');
    setFormDept(selectedDept || user?.department || 'CSE');
    setFormYear('2nd Year');
    setFormSection('A');
    setFormGender('Male');
    setFormEmail(user?.email || '');

    // If event has related products, default to first product but set buyProduct=false
    if (event.related_products && event.related_products.length > 0) {
      setSelectedProductId(event.related_products[0].id);
    } else {
      setSelectedProductId(null);
    }
    setBuyProduct(false);
    setIsRegisterOpen(true);
  };

  // Close Registration Modal
  const handleCloseRegister = () => {
    setIsRegisterOpen(false);
    setSelectedEvent(null);
  };

  // Registration Mutation
  const registerMutation = useMutation({
    mutationFn: (payload: StudentRegisterPayload) => studentPortalApi.register(payload),
    onSuccess: (data) => {
      toast.success(data.message || 'Successfully registered! Ticket generated.');
      queryClient.invalidateQueries({ queryKey: ['studentPortal'] });
      handleCloseRegister();
      setActiveTab('tickets'); // Switch to My Tickets so student can verify immediately
    },
    onError: (err: any) => {
      toast.error(err?.message || 'Registration failed. Please try again.');
    },
  });

  // Calculate pricing
  const eventPrice = selectedEvent?.price_inr || 0;
  const chosenProduct = selectedEvent?.related_products?.find((p) => p.id === selectedProductId);
  const productPrice = buyProduct && chosenProduct ? chosenProduct.price_inr : 0;
  const totalPayable = eventPrice + productPrice;

  // Submit Registration Form with optional Razorpay integration
  const handleSubmitRegistration = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEvent) return;

    if (!formName.trim() || !formEmail.trim() || !formSection.trim()) {
      toast.error('Please fill in all required fields (Name, Department, Year, Section, Gender, Email).');
      return;
    }

    const payload: StudentRegisterPayload = {
      event_id: selectedEvent.id,
      name: formName.trim(),
      department: formDept,
      year: formYear,
      section: formSection.trim().toUpperCase(),
      gender: formGender,
      email: formEmail.trim(),
      buy_product: buyProduct,
      product_id: buyProduct ? selectedProductId : null,
    };

    // If payment required (either event is paid or student decided to buy company product)
    if (totalPayable > 0) {
      setIsProcessingPayment(true);
      try {
        toast.info(`Opening Razorpay for ₹${totalPayable}...`);

        // 1. Create order on backend (creates Razorpay order / local test order)
        const orderRes = await studentPortalApi.createOrder({
          event_id: selectedEvent.id,
          buy_product: buyProduct,
          product_id: buyProduct ? selectedProductId : null,
        });

        if (orderRes.is_free) {
          registerMutation.mutate(payload);
          return;
        }

        // 2. Open official Razorpay checkout modal
        const checkoutResult = await openRazorpayCheckout(
          {
            key_id: orderRes.key_id,
            gateway_order_id: orderRes.gateway_order_id,
            amount: orderRes.amount,
            currency: orderRes.currency,
          },
          {
            name: formName.trim(),
            email: formEmail.trim(),
          },
        );

        if (checkoutResult.status === 'dismissed') {
          toast.info('Payment was cancelled. You have not been charged.');
          return;
        }

        // 3. Attach Razorpay payment details and complete registration in DB
        payload.razorpay_payment_id = checkoutResult.payment.razorpay_payment_id;
        payload.razorpay_order_id = checkoutResult.payment.razorpay_order_id;
        payload.razorpay_signature = checkoutResult.payment.razorpay_signature;

        toast.success(`Payment verified (${checkoutResult.payment.razorpay_payment_id})! Saving registration...`);
        registerMutation.mutate(payload);
      } catch (err: any) {
        toast.error(err?.message || 'Payment processing failed. Please try again.');
      } finally {
        setIsProcessingPayment(false);
      }
    } else {
      // Free Registration
      registerMutation.mutate(payload);
    }
  };

  const copyTicketCode = (code: string) => {
    navigator.clipboard.writeText(code);
    toast.success(`Copied ticket code: ${code}`);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Student Profile Header */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 text-white p-6 sm:p-10 shadow-xl border border-indigo-800/40">
        <div className="absolute top-0 right-0 -mr-16 -mt-16 w-80 h-80 rounded-full bg-indigo-500/15 blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-300 text-xs font-semibold border border-indigo-500/30">
              <GraduationCap className="w-3.5 h-3.5 text-indigo-400" />
              <span>Official Student Portal</span>
            </div>

            <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-white">
              Welcome, {user?.full_name || 'Student'}!
            </h1>

            <div className="flex flex-wrap items-center gap-4 text-xs sm:text-sm text-slate-300">
              <span className="flex items-center gap-1.5">
                <Mail className="w-4 h-4 text-indigo-400" />
                <strong className="text-white font-mono">{user?.email}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <Building2 className="w-4 h-4 text-indigo-400" />
                Selected Dept: <strong className="text-white">{selectedDept}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                Status: <strong className="text-emerald-400">Verified Student</strong>
              </span>
            </div>
          </div>

          {/* Navigation Pill Tabs */}
          <div className="flex items-center gap-2 bg-slate-800/80 p-1.5 rounded-2xl border border-slate-700/60">
            <button
              onClick={() => setActiveTab('events')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-sm transition-all ${
                activeTab === 'events'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Calendar className="w-4 h-4" />
              <span>Department Events</span>
            </button>
            <button
              onClick={() => setActiveTab('tickets')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-sm transition-all ${
                activeTab === 'tickets'
                  ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/30'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Ticket className="w-4 h-4" />
              <span>My Tickets ({myTickets.length})</span>
            </button>
          </div>
        </div>
      </div>

      {/* TAB 1: DEPARTMENT SELECTION & EVENTS */}
      {activeTab === 'events' && (
        <div className="space-y-6">
          {/* 1. College Departments Bar */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-indigo-600" />
                Select College Department:
              </h2>
              <span className="text-xs text-slate-500 font-medium">
                Click a department to view its events & registered students
              </span>
            </div>

            <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-9 gap-2">
              {DEPARTMENTS.map((dept) => {
                const isSelected = selectedDept === dept;
                const deptStat = deptSummaryData?.departments?.find((d) => d.department === dept);
                const regCount = deptStat?.registered_count || 0;

                return (
                  <button
                    key={dept}
                    onClick={() => setSelectedDept(dept)}
                    className={`relative p-3 rounded-2xl flex flex-col items-center justify-center gap-1 text-center transition-all border ${
                      isSelected
                        ? 'bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-600/25 scale-[1.03]'
                        : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200 hover:border-indigo-300'
                    }`}
                  >
                    <span className="font-extrabold text-sm tracking-wide">{dept}</span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                        isSelected ? 'bg-indigo-700 text-indigo-100' : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {regCount} Reg
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 2. Events List for Selected Department */}
          <Card className="border-slate-200">
            <CardHeader className="border-b border-slate-100 pb-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-xl font-black text-slate-900 flex items-center gap-2">
                    <span>{selectedDept} Department Events</span>
                    <span className="text-xs px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 font-bold border border-indigo-200">
                      {departmentEvents.length} Events
                    </span>
                  </CardTitle>
                  <CardDescription>
                    Browse events hosted by {selectedDept}, check registration numbers, and register below.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>

            <CardContent className="pt-6">
              {isEventsLoading ? (
                <div className="py-16 text-center text-slate-400">
                  <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                  <p className="text-sm font-medium">Loading {selectedDept} events...</p>
                </div>
              ) : departmentEvents.length === 0 ? (
                <div className="py-16 text-center bg-slate-50/50 rounded-2xl border border-dashed border-slate-200">
                  <Calendar className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <h3 className="text-base font-bold text-slate-800">No events found for {selectedDept} yet</h3>
                  <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                    New departmental symposiums, workshops, and competitions will appear here soon.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {departmentEvents.map((evt) => {
                    const isRegistered = evt.is_registered;

                    return (
                      <div
                        key={evt.id}
                        className="flex flex-col justify-between p-5 rounded-2xl border border-slate-200 hover:border-indigo-300 bg-white hover:shadow-lg transition-all group"
                      >
                        <div className="space-y-4">
                          {/* Banner & Badges */}
                          {evt.banner_url ? (
                            <div className="h-44 w-full rounded-xl overflow-hidden bg-slate-100 relative">
                              <img
                                src={evt.banner_url}
                                alt={evt.title}
                                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                              />
                              <div className="absolute top-3 left-3 flex gap-2">
                                <span className="px-2.5 py-1 rounded-lg bg-slate-900/80 backdrop-blur-md text-white text-xs font-bold">
                                  {evt.department}
                                </span>
                              </div>
                            </div>
                          ) : (
                            <div className="h-28 w-full rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 p-4 flex flex-col justify-end text-white relative">
                              <span className="absolute top-3 left-3 px-2.5 py-1 rounded-lg bg-black/30 backdrop-blur-md text-white text-xs font-bold">
                                {evt.department}
                              </span>
                            </div>
                          )}

                          {/* Event Details */}
                          <div>
                            <h3 className="text-lg font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">
                              {evt.title}
                            </h3>
                            <p className="text-xs text-slate-600 line-clamp-2 mt-1">
                              {evt.description || 'College technical & cultural event.'}
                            </p>
                          </div>

                          {/* Info Pills */}
                          <div className="space-y-2 pt-1 border-t border-slate-100 text-xs text-slate-600">
                            <div className="flex items-center gap-2">
                              <Calendar className="w-3.5 h-3.5 text-indigo-500" />
                              <span>{evt.starts_at ? formatDateTime(evt.starts_at) : 'Schedule announced soon'}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <MapPin className="w-3.5 h-3.5 text-indigo-500" />
                              <span>{evt.venue || 'Campus Auditorium'}</span>
                            </div>

                            {/* Registered Students Counter as requested */}
                            <div className="flex items-center justify-between pt-2">
                              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 font-bold text-xs border border-indigo-100">
                                <Users className="w-3.5 h-3.5" />
                                <span>{evt.registered_count} Students Registered from {evt.department}</span>
                              </div>
                              <span className="font-bold text-slate-800 text-sm">
                                {evt.price_inr === 0 ? 'FREE' : `₹${evt.price_inr}`}
                              </span>
                            </div>

                            {/* Related Company Product Banner if available */}
                            {evt.related_products && evt.related_products.length > 0 && (
                              <div className="p-2.5 rounded-xl bg-amber-50/80 border border-amber-200/80 text-[11px] text-amber-900 flex items-center justify-between gap-2">
                                <span className="flex items-center gap-1 font-semibold">
                                  <ShoppingBag className="w-3.5 h-3.5 text-amber-600" />
                                  Special Company Product Available ({evt.related_products[0].name})
                                </span>
                                <span className="font-bold">₹{evt.related_products[0].price_inr}</span>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Registration Button */}
                        <div className="pt-4 mt-3 border-t border-slate-100">
                          {isRegistered ? (
                            <div className="flex items-center justify-between">
                              <span className="inline-flex items-center gap-1.5 text-xs font-bold text-emerald-700 bg-emerald-50 px-3 py-1.5 rounded-xl border border-emerald-200">
                                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                Registered ({evt.user_ticket_code || 'Confirmed'})
                              </span>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setActiveTab('tickets')}
                                className="text-xs"
                              >
                                View My Ticket
                              </Button>
                            </div>
                          ) : (
                            <Button
                              onClick={() => handleOpenRegister(evt)}
                              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm shadow-md shadow-indigo-600/20"
                              leftIcon={<Ticket className="w-4 h-4" />}
                            >
                              Register for Event
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 2: MY TICKETS (FOR STUDENT VERIFICATION) */}
      {activeTab === 'tickets' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-black text-slate-900 flex items-center gap-2">
                <Ticket className="w-6 h-6 text-emerald-600" />
                <span>My Registered Tickets & Entry Verification Pass</span>
              </h2>
              <p className="text-xs sm:text-sm text-slate-500">
                All registered event tickets are stored in the database. Present this QR code or Ticket Code at the door for verification.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveTab('events')}
              leftIcon={<Calendar className="w-4 h-4" />}
            >
              Browse More Events
            </Button>
          </div>

          {isTicketsLoading ? (
            <div className="py-16 text-center text-slate-400">
              <div className="w-8 h-8 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-sm font-medium">Verifying tickets with database...</p>
            </div>
          ) : myTickets.length === 0 ? (
            <Card className="border-slate-200 text-center py-16">
              <CardContent className="space-y-4">
                <Ticket className="w-16 h-16 text-slate-300 mx-auto" />
                <div className="space-y-1">
                  <h3 className="text-lg font-bold text-slate-800">No Tickets Found</h3>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    You haven't registered for any events yet. Select a department from the events tab and register to get your official QR ticket.
                  </p>
                </div>
                <Button
                  onClick={() => setActiveTab('events')}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold"
                >
                  Explore Events
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {myTickets.map((t: StudentTicketItem) => (
                <div
                  key={t.ticket_id}
                  className="bg-white rounded-3xl border border-slate-200 shadow-lg overflow-hidden flex flex-col justify-between hover:border-emerald-400 transition-all"
                >
                  {/* Ticket Header Banner */}
                  <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 p-5 text-white flex items-center justify-between">
                    <div>
                      <span className="text-[10px] tracking-wider uppercase font-extrabold text-indigo-300 bg-indigo-900/60 px-2 py-0.5 rounded-md border border-indigo-700/50">
                        {t.event_department} DEPARTMENT
                      </span>
                      <h3 className="text-base font-extrabold text-white mt-1 leading-snug">
                        {t.event_title}
                      </h3>
                    </div>
                    <div className="text-right">
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                        {t.status === 'used' ? 'CHECKED IN' : 'CONFIRMED & REAL'}
                      </span>
                    </div>
                  </div>

                  {/* Ticket Body & QR Code for Door Verification */}
                  <div className="p-6 space-y-5">
                    <div className="flex flex-col sm:flex-row items-center gap-6 bg-slate-50 p-4 rounded-2xl border border-slate-200">
                      {/* Generated QR Code */}
                      <div className="p-2.5 bg-white rounded-xl shadow-sm border border-slate-200 flex-shrink-0">
                        <QRCodeSVG
                          value={t.ticket_code}
                          size={110}
                          level="H"
                          includeMargin={false}
                        />
                      </div>

                      {/* Ticket Code & Student Info */}
                      <div className="space-y-1.5 flex-1 text-center sm:text-left">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Official Ticket Code
                        </span>
                        <div className="flex items-center justify-center sm:justify-start gap-2">
                          <span className="font-mono font-black text-xl text-slate-900 tracking-wider">
                            {t.ticket_code}
                          </span>
                          <button
                            onClick={() => copyTicketCode(t.ticket_code)}
                            className="p-1 hover:bg-slate-200 rounded text-slate-500"
                            title="Copy Code"
                          >
                            <Copy className="w-4 h-4" />
                          </button>
                        </div>
                        <p className="text-xs text-slate-600 font-medium">
                          Name: <strong className="text-slate-900">{t.student_name}</strong>
                        </p>
                        <p className="text-xs text-slate-600 font-medium font-mono">
                          Email: <strong className="text-slate-900">{t.student_email}</strong>
                        </p>
                      </div>
                    </div>

                    {/* Meta Details Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs bg-slate-50/70 p-3.5 rounded-xl border border-slate-100">
                      <div>
                        <span className="text-slate-400 block text-[10px] font-bold">DEPARTMENT</span>
                        <span className="font-bold text-slate-800">{t.department}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] font-bold">YEAR</span>
                        <span className="font-bold text-slate-800">{t.year}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] font-bold">SECTION</span>
                        <span className="font-bold text-slate-800">Sec {t.section}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] font-bold">GENDER</span>
                        <span className="font-bold text-slate-800">{t.gender}</span>
                      </div>
                    </div>

                    {/* Product Purchase Status */}
                    {t.buy_product && (
                      <div className="p-3 bg-amber-50 rounded-xl border border-amber-200/80 flex items-center justify-between text-xs text-amber-900">
                        <span className="flex items-center gap-1.5 font-bold">
                          <ShoppingBag className="w-4 h-4 text-amber-600" />
                          Company Product: {t.product_name}
                        </span>
                        <span className="font-mono font-bold bg-amber-200/60 px-2 py-0.5 rounded text-[11px]">
                          PAID: ₹{t.total_paid_inr}
                        </span>
                      </div>
                    )}

                    {/* Payment Confirmation & Razorpay ID */}
                    <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-indigo-50/70 rounded-xl border border-indigo-100 text-xs">
                      <div className="flex items-center gap-1.5 font-medium text-slate-700">
                        <CreditCard className="w-4 h-4 text-indigo-600" />
                        <span>Payment Status:</span>
                        {t.payment_status === 'PAID' || (t.total_paid_inr && t.total_paid_inr > 0) ? (
                          <span className="font-extrabold text-emerald-800 bg-emerald-100 px-2.5 py-0.5 rounded-full text-[11px] border border-emerald-200">
                            ₹{t.total_paid_inr} PAID
                          </span>
                        ) : (
                          <span className="font-bold text-slate-700 bg-slate-200/80 px-2 py-0.5 rounded-full text-[11px]">
                            FREE
                          </span>
                        )}
                      </div>
                      {t.razorpay_payment_id && (
                        <div className="text-[11px] font-mono font-semibold text-indigo-800 bg-white px-2 py-0.5 rounded border border-indigo-200">
                          Razorpay: {t.razorpay_payment_id}
                        </div>
                      )}
                    </div>

                    {/* Event Timing & Venue */}
                    <div className="flex items-center justify-between text-xs text-slate-500 pt-2 border-t border-slate-100">
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3.5 h-3.5 text-slate-400" />
                        {t.event_venue || 'Main Auditorium'}
                      </span>
                      <span>
                        {t.event_starts_at ? formatDateTime(t.event_starts_at) : 'Date TBA'}
                      </span>
                    </div>
                  </div>

                  {/* Verification Status Footer */}
                  <div className="bg-slate-50 px-6 py-3 border-t border-slate-200 flex items-center justify-between text-xs">
                    <span className="text-slate-500 flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-emerald-600" />
                      Status: <strong className="text-slate-800 font-bold">Valid & Verified in DB</strong>
                    </span>
                    <span className="text-slate-400 text-[10px]">
                      Registered {t.registered_at ? new Date(t.registered_at).toLocaleDateString() : 'Recently'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* REGISTRATION FORM MODAL (with all required fields + Buy/Not Buy Product + Razorpay) */}
      {isRegisterOpen && selectedEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm overflow-y-auto">
          <div className="relative w-full max-w-2xl bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden my-8">
            {/* Modal Header */}
            <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 p-6 text-white flex items-center justify-between">
              <div>
                <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider">
                  Event Registration Form
                </span>
                <h3 className="text-xl font-black text-white mt-0.5">
                  {selectedEvent.title}
                </h3>
                <p className="text-xs text-slate-300">
                  Department: <strong className="text-white">{selectedEvent.department}</strong> | Venue: {selectedEvent.venue || 'Campus'}
                </p>
              </div>
              <button
                onClick={handleCloseRegister}
                className="p-2 rounded-full hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body / Form */}
            <form onSubmit={handleSubmitRegistration} className="p-6 sm:p-8 space-y-6">
              {/* Field 1: Full Name */}
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                  Student Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Enter your full name"
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm font-medium"
                />
              </div>

              {/* Two Column Grid: Department* & Which Year* */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Field 2: Department* */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                    Department <span className="text-rose-500">*</span>
                  </label>
                  <select
                    value={formDept}
                    onChange={(e) => setFormDept(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm font-medium bg-white"
                  >
                    {DEPARTMENTS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Field 3: Which Year* */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                    Which Year <span className="text-rose-500">*</span>
                  </label>
                  <select
                    value={formYear}
                    onChange={(e) => setFormYear(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm font-medium bg-white"
                  >
                    {YEARS.map((y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Two Column Grid: Section* & Gender* */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Field 4: Section* */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                    Section <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    maxLength={10}
                    value={formSection}
                    onChange={(e) => setFormSection(e.target.value)}
                    placeholder="e.g. A, B, C, D"
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm font-medium"
                  />
                </div>

                {/* Field 5: Gender* */}
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                    Gender <span className="text-rose-500">*</span>
                  </label>
                  <select
                    value={formGender}
                    onChange={(e) => setFormGender(e.target.value)}
                    className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm font-medium bg-white"
                  >
                    {GENDERS.map((g) => (
                      <option key={g} value={g}>
                        {g}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Field 6: Email ID* */}
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                  Email ID <span className="text-rose-500">*</span>
                </label>
                <input
                  type="email"
                  required
                  value={formEmail}
                  onChange={(e) => setFormEmail(e.target.value)}
                  placeholder="student@college.edu"
                  className="w-full px-4 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm font-medium font-mono"
                />
              </div>

              {/* RELATED COMPANY PRODUCT: BUY OR NOT BUY OPTION */}
              <div className="pt-4 border-t border-slate-200">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-extrabold text-slate-900 flex items-center gap-2">
                    <ShoppingBag className="w-4 h-4 text-indigo-600" />
                    Related Company Product for this Event
                  </h4>
                  <span className="text-[11px] text-slate-500">Optional add-on</span>
                </div>

                {selectedEvent.related_products && selectedEvent.related_products.length > 0 ? (
                  <div className="space-y-3">
                    {/* Product Card */}
                    {selectedEvent.related_products.map((prod) => {
                      const isSelectedProd = selectedProductId === prod.id;

                      return (
                        <div
                          key={prod.id}
                          className={`p-4 rounded-2xl border transition-all ${
                            buyProduct && isSelectedProd
                              ? 'bg-indigo-50/70 border-indigo-400 shadow-sm'
                              : 'bg-slate-50 border-slate-200'
                          }`}
                        >
                          <div className="flex items-center gap-4">
                            {prod.image_url ? (
                              <img
                                src={prod.image_url}
                                alt={prod.name}
                                className="w-14 h-14 object-cover rounded-xl border border-slate-200 flex-shrink-0"
                              />
                            ) : (
                              <div className="w-14 h-14 rounded-xl bg-indigo-100 flex items-center justify-center text-indigo-600 flex-shrink-0">
                                <ShoppingBag className="w-6 h-6" />
                              </div>
                            )}

                            <div className="flex-1">
                              <h5 className="font-bold text-sm text-slate-900">{prod.name}</h5>
                              <p className="text-xs text-slate-500 line-clamp-1">
                                {prod.description || 'Official event merchandise & kits.'}
                              </p>
                              <span className="font-bold text-indigo-700 text-sm mt-0.5 inline-block">
                                ₹{prod.price_inr}
                              </span>
                            </div>
                          </div>

                          {/* Buy vs Not Buy Buttons */}
                          <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-slate-200/80">
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedProductId(prod.id);
                                setBuyProduct(true);
                              }}
                              className={`py-2 px-3 rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition-all ${
                                buyProduct && isSelectedProd
                                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                                  : 'bg-white text-slate-700 border border-slate-300 hover:border-indigo-400'
                              }`}
                            >
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              Buy Product (+₹{prod.price_inr})
                            </button>

                            <button
                              type="button"
                              onClick={() => {
                                setBuyProduct(false);
                              }}
                              className={`py-2 px-3 rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition-all ${
                                !buyProduct
                                  ? 'bg-slate-700 text-white shadow-sm'
                                  : 'bg-white text-slate-700 border border-slate-300 hover:border-slate-400'
                              }`}
                            >
                              <X className="w-3.5 h-3.5" />
                              Not Buy (Event Only)
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="p-3.5 rounded-xl bg-slate-50 text-xs text-slate-500 border border-slate-200">
                    No special product assigned to this event. You can register directly.
                  </div>
                )}
              </div>

              {/* PAYMENT & SUMMARY BREAKDOWN */}
              <div className="p-4 rounded-2xl bg-slate-900 text-white space-y-2">
                <div className="flex justify-between text-xs text-slate-300">
                  <span>Event Registration Fee:</span>
                  <span className="font-mono font-bold">
                    {eventPrice === 0 ? 'FREE' : `₹${eventPrice}`}
                  </span>
                </div>
                {buyProduct && (
                  <div className="flex justify-between text-xs text-indigo-300">
                    <span>Company Product ({chosenProduct?.name}):</span>
                    <span className="font-mono font-bold">+₹{productPrice}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm font-black pt-2 border-t border-slate-800 text-white">
                  <span>Total Amount:</span>
                  <span className="font-mono text-emerald-400 text-base">
                    {totalPayable === 0 ? 'FREE REGISTRATION' : `₹${totalPayable}`}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleCloseRegister}
                  disabled={registerMutation.isPending || isProcessingPayment}
                >
                  Cancel
                </Button>

                <Button
                  type="submit"
                  isLoading={registerMutation.isPending || isProcessingPayment}
                  className={
                    totalPayable > 0
                      ? 'bg-indigo-600 hover:bg-indigo-700 text-white font-bold shadow-lg shadow-indigo-600/30'
                      : 'bg-emerald-600 hover:bg-emerald-700 text-white font-bold shadow-lg shadow-emerald-600/30'
                  }
                  leftIcon={totalPayable > 0 ? <CreditCard className="w-4 h-4" /> : <Ticket className="w-4 h-4" />}
                >
                  {isProcessingPayment
                    ? 'Connecting to Razorpay...'
                    : totalPayable > 0
                    ? `Pay with Razorpay & Register (₹${totalPayable})`
                    : 'Confirm Free Registration'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
