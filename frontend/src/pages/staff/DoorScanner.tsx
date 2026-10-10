import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Html5Qrcode } from 'html5-qrcode';
import { eventsApi } from '../../api/events';
import { ticketsApi } from '../../api/tickets';
import { useAuth } from '../../context/AuthContext';
import { hasMinimumRole } from '../../types/api';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { useToast } from '../../components/ui/Toast';
import { formatDate } from '../../lib/formatDate';
import type { CheckInResponse, EventItem } from '../../types/events';
import {
  Camera,
  CameraOff,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Search,
  Volume2,
  VolumeX,
  ShieldCheck,
  Calendar,
  Users,
} from 'lucide-react';

const LOCAL_STORAGE_EVENT_KEY = 'ssa_scanner_event_id';

// Synthesize short audio cues via Web Audio API (no external asset dependencies)
function playScanSound(type: 'valid' | 'invalid') {
  try {
    const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();

    if (type === 'valid') {
      // Pleasant high-pitch chime (chord or dual tone)
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime); // A5
      osc.frequency.exponentialRampToValueAtTime(1320, ctx.currentTime + 0.15); // E6
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
    } else {
      // Low buzz for errors
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(220, ctx.currentTime); // A3
      osc.frequency.linearRampToValueAtTime(180, ctx.currentTime + 0.25);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    }
  } catch {
    // Ignore audio permission/context errors silently
  }
}

export function DoorScanner() {
  const toast = useToast();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [rawSelectedEventId, setRawSelectedEventId] = useState<string>(() => {
    return localStorage.getItem(LOCAL_STORAGE_EVENT_KEY) || '';
  });

  const [manualCode, setManualCode] = useState('');
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [sessionScans, setSessionScans] = useState(0);

  // Arm's length result overlay state
  const [scanResult, setScanResult] = useState<CheckInResponse | null>(null);
  const [lastScannedCode, setLastScannedCode] = useState<string | null>(null);

  const html5QrCodeRef = useRef<Html5Qrcode | null>(null);
  const debounceRef = useRef<{ [code: string]: number }>({});
  const overlayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isOrganizer = user ? hasMinimumRole(user.role, 'organizer') : false;

  // 1. Fetch Events List for selection
  const { data: eventsData, isLoading: eventsLoading } = useQuery({
    queryKey: ['events', 'scanner-list'],
    queryFn: () => eventsApi.getEvents(),
  });

  const events = eventsData?.items || [];
  const selectedEventId = rawSelectedEventId || (events.length > 0 ? events[0].id : '');

  const handleEventChange = (eventId: string) => {
    setRawSelectedEventId(eventId);
    localStorage.setItem(LOCAL_STORAGE_EVENT_KEY, eventId);
    setScanResult(null);
  };

  const selectedEvent = events.find((e) => e.id === selectedEventId);

  // 2. Fetch event report metrics if organizer
  const { data: eventReport, refetch: refetchReport } = useQuery({
    queryKey: ['event-report', selectedEventId],
    queryFn: () => eventsApi.getEventReport(selectedEventId),
    enabled: !!selectedEventId && isOrganizer,
  });

  // 3. Check-In Mutation
  const checkInMutation = useMutation({
    mutationFn: (code: string) =>
      ticketsApi.checkIn({
        event_id: selectedEventId,
        code,
      }),
    onSuccess: (data, code) => {
      setLastScannedCode(code);
      setScanResult(data);
      setSessionScans((prev) => prev + 1);

      // Play audio cue
      if (soundEnabled) {
        if (data.result === 'VALID') {
          playScanSound('valid');
        } else {
          playScanSound('invalid');
        }
      }

      // Haptic feedback
      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        try {
          if (data.result === 'VALID') {
            navigator.vibrate([100]);
          } else {
            navigator.vibrate([100, 60, 120]);
          }
        } catch {
          // ignore
        }
      }

      // Refresh report if organizer
      if (isOrganizer) {
        refetchReport();
      }
      queryClient.invalidateQueries({ queryKey: ['tickets'] });

      // Auto dismiss overlay after 2.5s
      if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
      overlayTimerRef.current = setTimeout(() => {
        setScanResult(null);
      }, 2600);
    },
    onError: (err: any) => {
      if (soundEnabled) playScanSound('invalid');
      setScanResult({
        result: 'INVALID',
        ticket: null,
      });
      toast.show(err.message || 'Check-in request failed', 'error');

      if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
      overlayTimerRef.current = setTimeout(() => {
        setScanResult(null);
      }, 2600);
    },
  });

  // Process a ticket code with 3s debounce per code
  const processCode = useCallback(
    (rawCode: string) => {
      const code = rawCode.trim().toUpperCase();
      if (!code) return;

      if (!selectedEventId) {
        toast.show('Please select an event before scanning.', 'warning');
        return;
      }

      // Check 3-second debounce for duplicate code scans
      const now = Date.now();
      const lastScanned = debounceRef.current[code] || 0;
      if (now - lastScanned < 3000) {
        return; // Debounced
      }
      debounceRef.current[code] = now;

      checkInMutation.mutate(code);
    },
    [selectedEventId, checkInMutation, toast]
  );

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualCode.trim()) return;
    processCode(manualCode);
    setManualCode('');
  };

  // 4. Camera QR Scanner Setup
  const stopCamera = useCallback(async () => {
    if (html5QrCodeRef.current && html5QrCodeRef.current.isScanning) {
      try {
        await html5QrCodeRef.current.stop();
      } catch {
        // ignore
      }
    }
    setCameraActive(false);
  }, []);

  const startCamera = useCallback(async () => {
    setCameraError(null);
    setCameraActive(true);

    try {
      const qrScanner = new Html5Qrcode('door-scanner-reader');
      html5QrCodeRef.current = qrScanner;

      await qrScanner.start(
        { facingMode: 'environment' },
        {
          fps: 10,
          qrbox: { width: 260, height: 260 },
        },
        (decodedText) => {
          processCode(decodedText);
        },
        () => {
          // ignore frame miss
        }
      );
    } catch (err: any) {
      setCameraError(err?.message || 'Unable to access camera. Please check permissions or use manual entry.');
      setCameraActive(false);
    }
  }, [processCode]);

  // Clean up scanner on unmount
  useEffect(() => {
    return () => {
      if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
      if (html5QrCodeRef.current && html5QrCodeRef.current.isScanning) {
        html5QrCodeRef.current.stop().catch(() => {});
      }
    };
  }, []);

  const dismissOverlay = () => {
    if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
    setScanResult(null);
  };

  return (
    <div className="relative min-h-[calc(100vh-4rem)] bg-slate-950 text-slate-100 flex flex-col justify-between">
      {/* Top Header Bar */}
      <div className="border-b border-slate-800 bg-slate-900/90 backdrop-blur px-4 py-3 sm:px-6">
        <div className="max-w-4xl mx-auto flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center border border-emerald-500/30">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                Door Scanner
                <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
                  {user?.role}
                </span>
              </h1>
              <p className="text-xs text-slate-400">Rapid event entry validation</p>
            </div>
          </div>

          {/* Real-time Counter Stats */}
          <div className="flex items-center gap-2">
            {isOrganizer && eventReport ? (
              <div className="px-3 py-1.5 rounded-xl bg-emerald-950/60 border border-emerald-700/50 flex items-center gap-2">
                <Users className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-emerald-200">
                  {eventReport.checked_in} / {eventReport.sold} checked in
                </span>
                <span className="text-[11px] font-medium text-emerald-400/80">
                  ({eventReport.attendance_rate}%)
                </span>
              </div>
            ) : (
              <div className="px-3 py-1.5 rounded-xl bg-indigo-950/60 border border-indigo-700/50 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-indigo-400" />
                <span className="text-xs font-bold text-indigo-200">
                  Session Scans: {sessionScans}
                </span>
              </div>
            )}

            <button
              onClick={() => setSoundEnabled(!soundEnabled)}
              className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              title={soundEnabled ? 'Mute audio feedback' : 'Enable audio feedback'}
              aria-label="Toggle sound"
            >
              {soundEnabled ? <Volume2 className="w-4 h-4 text-emerald-400" /> : <VolumeX className="w-4 h-4 text-slate-400" />}
            </button>
          </div>
        </div>
      </div>

      {/* Main Scanner Section */}
      <div className="max-w-2xl w-full mx-auto px-4 py-6 flex-1 flex flex-col justify-center">
        {/* Event Selection dropdown */}
        <div className="mb-6">
          <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
            Active Event for Door Check-in
          </label>
          <div className="relative">
            <select
              value={selectedEventId}
              onChange={(e) => handleEventChange(e.target.value)}
              disabled={eventsLoading || events.length === 0}
              className="w-full bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-3 text-sm font-medium focus:ring-2 focus:ring-emerald-500 focus:outline-none appearance-none"
            >
              {eventsLoading ? (
                <option>Loading events...</option>
              ) : events.length === 0 ? (
                <option>No events available</option>
              ) : (
                events.map((ev: EventItem) => (
                  <option key={ev.id} value={ev.id}>
                    {ev.title} ({formatDate(ev.starts_at)}) • {ev.venue}
                  </option>
                ))
              )}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-slate-400">
              <Calendar className="w-4 h-4" />
            </div>
          </div>
          {selectedEvent && (
            <p className="mt-1.5 text-xs text-slate-400 flex items-center justify-between">
              <span>Venue: <strong className="text-slate-300">{selectedEvent.venue}</strong></span>
              <span>Status: <strong className="capitalize text-emerald-400">{selectedEvent.status}</strong></span>
            </p>
          )}
        </div>

        {/* Camera Viewfinder View */}
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-4 sm:p-6 mb-6 shadow-2xl relative overflow-hidden">
          {cameraActive ? (
            <div className="relative">
              {/* html5-qrcode element */}
              <div
                id="door-scanner-reader"
                className="w-full aspect-square max-h-[340px] rounded-2xl overflow-hidden bg-black mx-auto border-2 border-emerald-500/50"
              />
              <div className="mt-4 flex items-center justify-between gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={stopCamera}
                  leftIcon={<CameraOff className="w-4 h-4 text-rose-400" />}
                  className="bg-slate-800 border-slate-700 text-slate-300"
                >
                  Turn Camera Off
                </Button>

                <p className="text-xs text-emerald-400 font-medium flex items-center gap-1.5 animate-pulse">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  Align ticket QR code in box
                </p>
              </div>
            </div>
          ) : (
            <div className="py-10 text-center">
              <div className="w-16 h-16 rounded-2xl bg-slate-800 text-emerald-400 flex items-center justify-center mx-auto mb-4 border border-slate-700 shadow-inner">
                <Camera className="w-8 h-8" />
              </div>
              <h3 className="text-lg font-bold text-white mb-1">Camera Scanner Ready</h3>
              <p className="text-xs text-slate-400 max-w-sm mx-auto mb-5">
                Enable your device camera for hands-free, instant verification of student attendee QR codes.
              </p>
              <Button
                variant="primary"
                onClick={startCamera}
                leftIcon={<Camera className="w-4 h-4" />}
                className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold"
              >
                Start Camera Scanner
              </Button>
            </div>
          )}

          {cameraError && (
            <div className="mt-4 p-3 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{cameraError}</span>
            </div>
          )}
        </div>

        {/* Manual Ticket Code Entry Form */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-4">
          <form onSubmit={handleManualSubmit} className="flex gap-2">
            <div className="relative flex-1">
              <Input
                type="text"
                placeholder="Or enter ticket code (e.g. ANNU-1042)"
                value={manualCode}
                onChange={(e) => setManualCode(e.target.value.toUpperCase())}
                className="w-full bg-slate-950 border-slate-700 text-white placeholder-slate-500 font-mono text-sm tracking-wide"
              />
            </div>
            <Button
              type="submit"
              variant="outline"
              disabled={checkInMutation.isPending || !manualCode.trim()}
              leftIcon={<Search className="w-4 h-4" />}
              className="bg-slate-800 border-slate-700 text-white font-semibold hover:bg-slate-700"
            >
              Verify Pass
            </Button>
          </form>
        </div>
      </div>

      {/* Arm's Length Full-Screen Result Overlay (DESIGN.md §6 door scanner specs) */}
      {scanResult && (
        <div
          onClick={dismissOverlay}
          className={`fixed inset-0 z-50 flex flex-col items-center justify-center p-6 text-white cursor-pointer select-none transition-all duration-200 animate-in fade-in zoom-in-95 ${
            scanResult.result === 'VALID'
              ? 'bg-emerald-600'
              : scanResult.result === 'ALREADY_USED'
              ? 'bg-amber-600'
              : scanResult.result === 'WRONG_EVENT'
              ? 'bg-blue-600'
              : 'bg-rose-600'
          }`}
          role="dialog"
          aria-live="assertive"
        >
          {/* Top Dismiss Hint */}
          <div className="absolute top-6 text-xs uppercase tracking-widest font-black opacity-80">
            Tap anywhere to dismiss
          </div>

          <div className="text-center max-w-lg mx-auto flex flex-col items-center">
            {/* Big Status Icon */}
            <div className="w-24 h-24 sm:w-32 sm:h-32 rounded-full bg-white/20 backdrop-blur flex items-center justify-center mb-6 shadow-2xl border-4 border-white/30 animate-bounce">
              {scanResult.result === 'VALID' && <CheckCircle2 className="w-16 h-16 sm:w-20 sm:h-20 text-white" />}
              {scanResult.result === 'ALREADY_USED' && <AlertTriangle className="w-16 h-16 sm:w-20 sm:h-20 text-white" />}
              {scanResult.result === 'WRONG_EVENT' && <AlertTriangle className="w-16 h-16 sm:w-20 sm:h-20 text-white" />}
              {scanResult.result === 'INVALID' && <XCircle className="w-16 h-16 sm:w-20 sm:h-20 text-white" />}
            </div>

            {/* Giant Big Header Readable at arm's length */}
            <h2 className="text-4xl sm:text-6xl font-black tracking-tight mb-2 uppercase drop-shadow-md">
              {scanResult.result === 'VALID' && 'ADMIT 1'}
              {scanResult.result === 'ALREADY_USED' && 'ALREADY USED'}
              {scanResult.result === 'WRONG_EVENT' && 'WRONG EVENT'}
              {scanResult.result === 'INVALID' && 'INVALID TICKET'}
            </h2>

            {/* Subtitle / Details */}
            {scanResult.result === 'VALID' && scanResult.ticket && (
              <div className="mt-4 space-y-2">
                <p className="text-2xl sm:text-3xl font-extrabold text-white/95">
                  {scanResult.ticket.user_name || 'Attendee'}
                </p>
                <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/20 font-bold text-sm tracking-wide">
                  <span>{scanResult.ticket.ticket_type_name}</span>
                  {scanResult.ticket.is_member_price && (
                    <span className="bg-amber-300 text-slate-900 text-[10px] uppercase font-black px-2 py-0.5 rounded-full">
                      Member Pass
                    </span>
                  )}
                </div>
                <p className="text-xs font-mono opacity-80 mt-1">Code: {scanResult.ticket.code}</p>
              </div>
            )}

            {scanResult.result === 'ALREADY_USED' && (
              <div className="mt-4 space-y-2">
                <p className="text-xl sm:text-2xl font-bold">
                  Previously Checked In
                </p>
                <p className="text-sm font-medium opacity-90">
                  Scanned: {scanResult.checked_in_at ? formatDate(scanResult.checked_in_at) : 'Earlier today'}
                </p>
                {scanResult.ticket?.user_name && (
                  <p className="text-sm opacity-80">Attendee: {scanResult.ticket.user_name}</p>
                )}
                <p className="text-xs font-mono opacity-70">Code: {scanResult.ticket?.code || lastScannedCode}</p>
              </div>
            )}

            {scanResult.result === 'WRONG_EVENT' && (
              <div className="mt-4 space-y-2">
                <p className="text-xl sm:text-2xl font-bold">
                  Ticket Belongs To Another Event
                </p>
                <p className="text-sm opacity-90">
                  Event: {scanResult.ticket?.event_title || 'Different Event'}
                </p>
                <p className="text-xs font-mono opacity-70">Code: {scanResult.ticket?.code || lastScannedCode}</p>
              </div>
            )}

            {scanResult.result === 'INVALID' && (
              <div className="mt-4 space-y-2">
                <p className="text-xl font-bold">No valid record found in database</p>
                <p className="text-sm opacity-80">Check ticket code spelling or re-issue pass</p>
                <p className="text-xs font-mono opacity-70">Code: {lastScannedCode}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
