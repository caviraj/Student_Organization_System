import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Html5Qrcode } from 'html5-qrcode';
import { staffPortalApi, type VerifyTicketResult, type StaffDepartmentStudent } from '../../api/staffPortal';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { useToast } from '../../components/ui/Toast';
import {
  Camera,
  CameraOff,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  QrCode,
  Users,
  Building2,
  Mail,
  User,
  GraduationCap,
  Volume2,
  VolumeX,
  History,
  ShieldCheck,
  Search,
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

// Audio feedback cues
function playScanSound(type: 'real' | 'fake') {
  try {
    const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();

    if (type === 'real') {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
    } else {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(220, ctx.currentTime);
      osc.frequency.linearRampToValueAtTime(160, ctx.currentTime + 0.3);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    }
  } catch {
    // Ignore audio permission errors
  }
}

export function DoorScanner() {
  const toast = useToast();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // ONLY TWO OPTIONS as required:
  // Option 1: 'scanning' (Ticket Scanning: Real or Fake check)
  // Option 2: 'registered' (Student Event Registered by department)
  const [currentOption, setCurrentOption] = useState<'scanning' | 'registered'>('scanning');

  // Option 1 State: Scanner
  const [manualCode, setManualCode] = useState('');
  const [cameraActive, setCameraActive] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [scanResult, setScanResult] = useState<VerifyTicketResult | null>(null);
  const [scanHistory, setScanHistory] = useState<VerifyTicketResult[]>([]);

  const html5QrCodeRef = useRef<Html5Qrcode | null>(null);
  const debounceRef = useRef<{ [code: string]: number }>({});

  // Option 2 State: Registered Students
  const [selectedDept, setSelectedDept] = useState<string>('CSE');
  const [studentSearch, setStudentSearch] = useState('');

  // Option 2 Queries
  const { data: deptListData } = useQuery({
    queryKey: ['staffPortal', 'departments'],
    queryFn: () => staffPortalApi.getDepartments(),
  });

  const { data: deptStudentsData, isLoading: isStudentsLoading } = useQuery({
    queryKey: ['staffPortal', 'deptStudents', selectedDept],
    queryFn: () => staffPortalApi.getDepartmentStudents(selectedDept),
    enabled: currentOption === 'registered' && !!selectedDept,
  });

  const deptStudents = deptStudentsData?.students || [];

  // Verify Ticket Mutation (Real vs Fake check against DB)
  const verifyMutation = useMutation({
    mutationFn: (code: string) => staffPortalApi.verifyTicket(code, true),
    onSuccess: (data) => {
      setScanResult(data);
      setScanHistory((prev) => [data, ...prev.slice(0, 19)]); // keep last 20 scans
      if (soundEnabled) {
        playScanSound(data.is_real ? 'real' : 'fake');
      }

      if (data.is_real) {
        toast.success(`REAL TICKET: ${data.student_name} (${data.student_email})`);
        queryClient.invalidateQueries({ queryKey: ['staffPortal'] });
      } else {
        toast.error('FAKE TICKET! Not found in database.');
      }
    },
    onError: (err: any) => {
      toast.error(err?.message || 'Verification request failed');
    },
  });

  // Handle Manual Code Check
  const handleManualVerify = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = manualCode.trim();
    if (!clean) return;
    verifyMutation.mutate(clean);
    setManualCode('');
  };

  // Start Camera Scanner
  const startCamera = async () => {
    try {
      if (html5QrCodeRef.current) {
        await html5QrCodeRef.current.stop();
        html5QrCodeRef.current = null;
      }

      const qrScanner = new Html5Qrcode('staff-qr-reader');
      html5QrCodeRef.current = qrScanner;

      await qrScanner.start(
        { facingMode: 'environment' },
        {
          fps: 10,
          qrbox: { width: 260, height: 260 },
          aspectRatio: 1.0,
        },
        (decodedText) => {
          const now = Date.now();
          const cleanText = decodedText.trim();
          const lastScanned = debounceRef.current[cleanText] || 0;
          if (now - lastScanned < 3000) {
            return; // 3 second debounce per ticket
          }
          debounceRef.current[cleanText] = now;
          verifyMutation.mutate(cleanText);
        },
        () => {
          // Frame read callback, intentionally ignored
        }
      );

      setCameraActive(true);
    } catch (err: any) {
      toast.error('Unable to start camera. Please verify permissions or use manual code entry.');
      setCameraActive(false);
    }
  };

  // Stop Camera Scanner
  const stopCamera = async () => {
    if (html5QrCodeRef.current) {
      try {
        await html5QrCodeRef.current.stop();
        html5QrCodeRef.current = null;
      } catch {
        // Ignored
      }
    }
    setCameraActive(false);
  };

  useEffect(() => {
    return () => {
      if (html5QrCodeRef.current) {
        html5QrCodeRef.current.stop().catch(() => {});
      }
    };
  }, []);

  // Filter students in Option 2
  const filteredStudents = deptStudents.filter((st: StaffDepartmentStudent) => {
    if (!studentSearch.trim()) return true;
    const query = studentSearch.toLowerCase();
    return (
      st.student_name.toLowerCase().includes(query) ||
      st.student_email.toLowerCase().includes(query) ||
      st.ticket_code.toLowerCase().includes(query) ||
      st.event_title.toLowerCase().includes(query)
    );
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Staff Portal Header */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 text-white p-6 sm:p-10 shadow-xl border border-slate-700">
        <div className="absolute top-0 right-0 -mr-16 -mt-16 w-80 h-80 rounded-full bg-indigo-500/10 blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-300 text-xs font-semibold border border-indigo-500/30">
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
              <span>Official Staff & Volunteer Portal</span>
            </div>

            <h1 className="text-2xl sm:text-4xl font-black tracking-tight text-white">
              Staff Door Control & Student Registration Portal
            </h1>

            <div className="flex flex-wrap items-center gap-4 text-xs sm:text-sm text-slate-300">
              <span className="flex items-center gap-1.5">
                <User className="w-4 h-4 text-indigo-400" />
                Staff: <strong className="text-white">{user?.full_name || 'Staff Member'}</strong>
              </span>
              <span className="flex items-center gap-1.5">
                <Mail className="w-4 h-4 text-indigo-400" />
                <span className="font-mono text-slate-300">{user?.email}</span>
              </span>
              <span className="flex items-center gap-1.5">
                <GraduationCap className="w-4 h-4 text-emerald-400" />
                Role: <strong className="text-emerald-400 capitalize">{user?.role}</strong>
              </span>
            </div>
          </div>

          {/* EXACTLY TWO OPTIONS AS REQUESTED BY USER */}
          <div className="flex flex-col sm:flex-row gap-2 bg-slate-900/90 p-2 rounded-2xl border border-slate-700">
            {/* Option 1: Ticket Scanning (Real or Fake) */}
            <button
              onClick={() => {
                setCurrentOption('scanning');
              }}
              className={`flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-black text-sm transition-all ${
                currentOption === 'scanning'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 scale-[1.02]'
                  : 'text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              <QrCode className="w-5 h-5 text-indigo-300" />
              <span>Option 1: Ticket Scanning (Real / Fake)</span>
            </button>

            {/* Option 2: Student Event Registered */}
            <button
              onClick={() => {
                if (cameraActive) stopCamera();
                setCurrentOption('registered');
              }}
              className={`flex items-center justify-center gap-2 px-6 py-3 rounded-xl font-black text-sm transition-all ${
                currentOption === 'registered'
                  ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/30 scale-[1.02]'
                  : 'text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              <Users className="w-5 h-5 text-emerald-300" />
              <span>Option 2: Student Event Registered</span>
            </button>
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* OPTION 1: TICKET SCANNING (REAL OR FAKE DATABASE CHECK)     */}
      {/* ============================================================ */}
      {currentOption === 'scanning' && (
        <div className="space-y-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Scanner Left Panel: QR Scanner & Manual Input (5 cols) */}
            <div className="lg:col-span-5 space-y-6">
              <Card className="border-slate-200">
                <CardHeader className="pb-3 border-b border-slate-100">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-lg font-black text-slate-900 flex items-center gap-2">
                        <QrCode className="w-5 h-5 text-indigo-600" />
                        <span>Scan Student QR Code</span>
                      </CardTitle>
                      <CardDescription>
                        Scan QR code with camera or enter the ticket code manually.
                      </CardDescription>
                    </div>
                    <button
                      onClick={() => setSoundEnabled(!soundEnabled)}
                      className={`p-2 rounded-xl border text-xs font-bold flex items-center gap-1 ${
                        soundEnabled
                          ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
                          : 'bg-slate-100 border-slate-200 text-slate-400'
                      }`}
                      title={soundEnabled ? 'Mute Chimes' : 'Enable Chimes'}
                    >
                      {soundEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
                    </button>
                  </div>
                </CardHeader>

                <CardContent className="pt-4 space-y-5">
                  {/* Camera Viewport Container */}
                  <div className="relative bg-slate-950 rounded-2xl overflow-hidden aspect-square flex flex-col items-center justify-center border-2 border-slate-800">
                    <div id="staff-qr-reader" className="w-full h-full" />

                    {!cameraActive && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center text-slate-400 space-y-3 bg-slate-950/90">
                        <CameraOff className="w-12 h-12 text-slate-600" />
                        <div>
                          <p className="text-sm font-bold text-white">Camera is Turned Off</p>
                          <p className="text-xs text-slate-400 mt-1">
                            Click below to start live QR scanning, or type ticket code below.
                          </p>
                        </div>
                        <Button
                          onClick={startCamera}
                          className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs"
                          leftIcon={<Camera className="w-4 h-4" />}
                        >
                          Turn On Camera
                        </Button>
                      </div>
                    )}

                    {cameraActive && (
                      <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between px-3 py-1.5 rounded-xl bg-slate-900/80 backdrop-blur-md text-white text-xs">
                        <span className="flex items-center gap-1.5 font-medium">
                          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                          Camera Active
                        </span>
                        <button
                          onClick={stopCamera}
                          className="text-rose-400 hover:text-rose-300 font-bold"
                        >
                          Stop
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Manual Ticket Code Entry Form */}
                  <form onSubmit={handleManualVerify} className="space-y-3">
                    <label className="block text-xs font-extrabold uppercase tracking-wider text-slate-700">
                      Or Enter Ticket Code Manually:
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={manualCode}
                        onChange={(e) => setManualCode(e.target.value)}
                        placeholder="e.g. SSA-A1B2C3D4 or code"
                        className="flex-1 px-4 py-2.5 rounded-xl border border-slate-300 focus:ring-2 focus:ring-indigo-500 text-sm font-mono font-bold uppercase"
                      />
                      <Button
                        type="submit"
                        isLoading={verifyMutation.isPending}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold"
                      >
                        Verify
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            </div>

            {/* Scanner Right Panel: Real or Fake Result Banner (7 cols) */}
            <div className="lg:col-span-7 space-y-6">
              {/* If no scan performed yet */}
              {!scanResult && (
                <div className="h-full min-h-[350px] flex flex-col items-center justify-center p-8 bg-slate-50 rounded-3xl border-2 border-dashed border-slate-200 text-center text-slate-400 space-y-3">
                  <ShieldCheck className="w-16 h-16 text-slate-300" />
                  <h3 className="text-base font-bold text-slate-700">Ready to Scan Tickets</h3>
                  <p className="text-xs text-slate-500 max-w-md">
                    Scan any student ticket QR code or enter ticket code. The system will verify against the database and display whether it is <strong>REAL</strong> or <strong>FAKE</strong> along with the student's <strong>Email ID and Name</strong>.
                  </p>
                </div>
              )}

              {/* REAL TICKET DISPLAY (PROMINENT STUDENT NAME & EMAIL) */}
              {scanResult && scanResult.is_real && (
                <div className="rounded-3xl border-4 border-emerald-500 bg-white shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                  {/* Top Green Banner */}
                  <div className="bg-emerald-600 text-white p-6 sm:p-8 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-14 h-14 rounded-2xl bg-white/20 flex items-center justify-center text-white flex-shrink-0">
                        <CheckCircle2 className="w-9 h-9" />
                      </div>
                      <div>
                        <span className="text-xs font-black uppercase tracking-wider text-emerald-200 bg-emerald-800/60 px-2.5 py-0.5 rounded-md">
                          DATABASE VERIFIED
                        </span>
                        <h2 className="text-2xl sm:text-3xl font-black text-white mt-1">
                          REAL TICKET!
                        </h2>
                        <p className="text-xs text-emerald-100 font-medium">
                          {scanResult.message}
                        </p>
                      </div>
                    </div>

                    <div className="text-right">
                      <span className="font-mono font-black text-lg sm:text-xl bg-white text-emerald-800 px-3 py-1 rounded-xl shadow-sm inline-block">
                        {scanResult.ticket_code}
                      </span>
                    </div>
                  </div>

                  {/* PROMINENT STUDENT DETAILS AS REQUESTED (NAME & EMAIL ID) */}
                  <div className="p-6 sm:p-8 space-y-6">
                    {/* Student Identity Highlight Box */}
                    <div className="p-5 rounded-2xl bg-gradient-to-r from-emerald-50 via-teal-50 to-indigo-50 border-2 border-emerald-300 space-y-3">
                      <span className="text-[10px] font-black tracking-wider uppercase text-emerald-700">
                        STUDENT CREDENTIALS (FROM DATABASE)
                      </span>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {/* Student Name */}
                        <div>
                          <span className="text-xs text-slate-500 font-semibold block">Student Name:</span>
                          <span className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
                            {scanResult.student_name}
                          </span>
                        </div>

                        {/* Student Email ID */}
                        <div>
                          <span className="text-xs text-slate-500 font-semibold block">Student Email ID:</span>
                          <span className="text-base sm:text-lg font-mono font-black text-indigo-700 break-all">
                            {scanResult.student_email}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Department, Year, Section, Gender Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs bg-slate-50 p-4 rounded-xl border border-slate-200">
                      <div>
                        <span className="text-slate-400 block text-[10px] font-bold">DEPARTMENT</span>
                        <span className="font-extrabold text-slate-800 text-sm">{scanResult.department}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] font-bold">YEAR</span>
                        <span className="font-extrabold text-slate-800 text-sm">{scanResult.year}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] font-bold">SECTION</span>
                        <span className="font-extrabold text-slate-800 text-sm">Sec {scanResult.section}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 block text-[10px] font-bold">GENDER</span>
                        <span className="font-extrabold text-slate-800 text-sm">{scanResult.gender}</span>
                      </div>
                    </div>

                    {/* Event Info */}
                    <div className="p-4 rounded-xl bg-slate-100/70 border border-slate-200 text-xs space-y-1">
                      <span className="text-slate-400 block text-[10px] font-bold uppercase">REGISTERED EVENT</span>
                      <h4 className="font-extrabold text-slate-900 text-sm">{scanResult.event_title}</h4>
                      <p className="text-slate-600">
                        Venue: <strong>{scanResult.event_venue || 'Main Auditorium'}</strong> | Dept: <strong>{scanResult.event_department}</strong>
                      </p>
                    </div>

                    {/* Payment & Fee Details */}
                    <div className="p-3 bg-indigo-50/80 rounded-xl border border-indigo-200 text-xs flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-black uppercase tracking-wider text-slate-500">PAYMENT & FEE:</span>
                        {scanResult.payment_status === 'PAID' || (scanResult.total_paid_inr && scanResult.total_paid_inr > 0) ? (
                          <span className="font-extrabold text-emerald-800 bg-emerald-100 px-2.5 py-0.5 rounded-full text-xs border border-emerald-300">
                            ₹{scanResult.total_paid_inr || 0} PAID
                          </span>
                        ) : (
                          <span className="font-bold text-slate-700 bg-slate-200 px-2.5 py-0.5 rounded-full text-xs">
                            FREE
                          </span>
                        )}
                      </div>
                      {scanResult.razorpay_payment_id && (
                        <div className="font-mono text-xs text-indigo-900 bg-white px-2.5 py-0.5 rounded-md border border-indigo-200 font-bold shadow-sm">
                          Razorpay: {scanResult.razorpay_payment_id}
                        </div>
                      )}
                    </div>

                    {/* Product Bought Info if any */}
                    {scanResult.product_bought && (
                      <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-900 flex items-center justify-between">
                        <span className="font-bold">
                          Company Product: {scanResult.product_name}
                        </span>
                        <span className="font-bold text-amber-700 bg-amber-200/60 px-2 py-0.5 rounded">
                          Hand over Product to Student
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* FAKE TICKET DISPLAY (BRIGHT RED ALERT) */}
              {scanResult && !scanResult.is_real && (
                <div className="rounded-3xl border-4 border-rose-600 bg-white shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                  <div className="bg-rose-600 text-white p-6 sm:p-8 flex items-center gap-5">
                    <div className="w-16 h-16 rounded-2xl bg-white/20 flex items-center justify-center text-white flex-shrink-0 animate-bounce">
                      <XCircle className="w-10 h-10" />
                    </div>
                    <div>
                      <span className="text-xs font-black uppercase tracking-wider text-rose-200 bg-rose-800/60 px-2.5 py-0.5 rounded-md">
                        SECURITY ALERT
                      </span>
                      <h2 className="text-2xl sm:text-4xl font-black text-white mt-1">
                        FAKE TICKET DETECTED!
                      </h2>
                      <p className="text-sm text-rose-100 font-semibold mt-1">
                        {scanResult.message}
                      </p>
                    </div>
                  </div>

                  <div className="p-6 sm:p-8 space-y-4">
                    <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-900 space-y-2">
                      <div className="flex items-center gap-2 font-bold text-sm">
                        <AlertTriangle className="w-5 h-5 text-rose-600" />
                        <span>Ticket Code Does Not Exist in Database!</span>
                      </div>
                      <p className="text-xs text-rose-700">
                        Scanned Code: <strong className="font-mono text-rose-900">{scanResult.scanned_code}</strong>
                      </p>
                      <p className="text-xs text-rose-600">
                        Do NOT admit this person. This QR code or ticket is counterfeit and was not officially issued by the college portal.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Recent Scan History */}
              {scanHistory.length > 0 && (
                <Card className="border-slate-200">
                  <CardHeader className="py-3 px-5 border-b border-slate-100 flex flex-row items-center justify-between">
                    <CardTitle className="text-xs font-black uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                      <History className="w-4 h-4 text-slate-400" />
                      <span>Recent Session Scans ({scanHistory.length})</span>
                    </CardTitle>
                    <button
                      onClick={() => setScanHistory([])}
                      className="text-[11px] text-slate-400 hover:text-slate-600 font-bold"
                    >
                      Clear
                    </button>
                  </CardHeader>
                  <CardContent className="p-0 divide-y divide-slate-100 max-h-60 overflow-y-auto">
                    {scanHistory.map((item, idx) => (
                      <div key={idx} className="p-3.5 flex items-center justify-between text-xs hover:bg-slate-50">
                        <div className="flex items-center gap-3">
                          {item.is_real ? (
                            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                          ) : (
                            <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                          )}
                          <div>
                            <span className="font-bold text-slate-800">
                              {item.is_real ? item.student_name : `FAKE: ${item.scanned_code}`}
                            </span>
                            {item.is_real && (
                              <span className="text-[11px] text-slate-500 block font-mono">
                                {item.student_email}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="text-right">
                          <span
                            className={`font-bold px-2 py-0.5 rounded text-[10px] ${
                              item.is_real
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            {item.is_real ? 'REAL' : 'FAKE'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ */}
      {/* OPTION 2: STUDENT EVENT REGISTERED BY DEPARTMENT             */}
      {/* ============================================================ */}
      {currentOption === 'registered' && (
        <div className="space-y-6">
          {/* Department Selection Bar */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-emerald-600" />
                Select Department to View Registered Students:
              </h2>
              <span className="text-xs text-slate-500 font-medium">
                Click a department to display all student registrations
              </span>
            </div>

            <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-9 gap-2">
              {DEPARTMENTS.map((dept) => {
                const isSelected = selectedDept === dept;
                const deptSummary = deptListData?.departments?.find((d) => d.department === dept);
                const regCount = deptSummary?.registered_students_count || 0;

                return (
                  <button
                    key={dept}
                    onClick={() => setSelectedDept(dept)}
                    className={`relative p-3 rounded-2xl flex flex-col items-center justify-center gap-1 text-center transition-all border ${
                      isSelected
                        ? 'bg-emerald-600 text-white border-emerald-600 shadow-md shadow-emerald-600/25 scale-[1.03]'
                        : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200 hover:border-emerald-300'
                    }`}
                  >
                    <span className="font-extrabold text-sm tracking-wide">{dept}</span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                        isSelected ? 'bg-emerald-700 text-emerald-100' : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {regCount} Students
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Registered Students Table Card */}
          <Card className="border-slate-200">
            <CardHeader className="border-b border-slate-100 pb-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <CardTitle className="text-xl font-black text-slate-900 flex items-center gap-2">
                    <span>{selectedDept} Department - Registered Students</span>
                    <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 font-bold border border-emerald-200">
                      {filteredStudents.length} Students
                    </span>
                  </CardTitle>
                  <CardDescription>
                    All registered student records saved in the database for {selectedDept}.
                  </CardDescription>
                </div>

                {/* Search Bar */}
                <div className="relative w-full sm:w-72">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={studentSearch}
                    onChange={(e) => setStudentSearch(e.target.value)}
                    placeholder="Search name, email, code..."
                    className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-300 focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>
            </CardHeader>

            <CardContent className="p-0">
              {isStudentsLoading ? (
                <div className="py-16 text-center text-slate-400">
                  <div className="w-8 h-8 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                  <p className="text-sm font-medium">Loading {selectedDept} registered students from database...</p>
                </div>
              ) : filteredStudents.length === 0 ? (
                <div className="py-16 text-center text-slate-500">
                  <Users className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <p className="text-sm font-bold text-slate-700">No registered students found for {selectedDept}</p>
                  <p className="text-xs text-slate-400 mt-1">
                    When students register for {selectedDept} events in the student portal, they will appear here.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-[11px] font-black text-slate-500 uppercase tracking-wider">
                        <th className="py-3 px-4">Student Name</th>
                        <th className="py-3 px-4">Email ID</th>
                        <th className="py-3 px-4">Year & Sec</th>
                        <th className="py-3 px-4">Gender</th>
                        <th className="py-3 px-4">Event Registered</th>
                        <th className="py-3 px-4">Ticket Code</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4">Payment & Fee</th>
                        <th className="py-3 px-4">Product</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-xs">
                      {filteredStudents.map((st: StaffDepartmentStudent) => (
                        <tr key={st.ticket_id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-3 px-4 font-bold text-slate-900">
                            {st.student_name}
                          </td>
                          <td className="py-3 px-4 font-mono text-indigo-700 font-semibold">
                            {st.student_email}
                          </td>
                          <td className="py-3 px-4 text-slate-700">
                            {st.year} - Sec {st.section}
                          </td>
                          <td className="py-3 px-4 text-slate-600">
                            {st.gender}
                          </td>
                          <td className="py-3 px-4 font-medium text-slate-800">
                            {st.event_title}
                          </td>
                          <td className="py-3 px-4 font-mono font-bold text-slate-900">
                            {st.ticket_code}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`px-2.5 py-1 rounded-full text-[10px] font-extrabold ${
                                st.status === 'used'
                                  ? 'bg-slate-200 text-slate-700'
                                  : 'bg-emerald-100 text-emerald-800'
                              }`}
                            >
                              {st.status === 'used' ? 'CHECKED IN' : 'VALID'}
                            </span>
                          </td>
                          <td className="py-3 px-4 whitespace-nowrap">
                            {st.payment_status === 'PAID' || (st.total_paid_inr && st.total_paid_inr > 0) ? (
                              <div>
                                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-black bg-emerald-100 text-emerald-800 border border-emerald-300">
                                  ₹{st.total_paid_inr || 0} PAID
                                </span>
                                {st.razorpay_payment_id && (
                                  <div className="text-[10px] font-mono text-indigo-800 font-bold mt-0.5">
                                    {st.razorpay_payment_id}
                                  </div>
                                )}
                              </div>
                            ) : (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">
                                FREE
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-4">
                            {st.product_bought ? (
                              <span className="text-[10px] font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded">
                                {st.product_name || 'Yes'}
                              </span>
                            ) : (
                              <span className="text-slate-400 text-[10px]">-</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
