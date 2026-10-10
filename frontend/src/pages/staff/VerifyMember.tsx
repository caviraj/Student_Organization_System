import { useState, useEffect, useRef, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Html5Qrcode } from 'html5-qrcode';
import { membershipsApi } from '../../api/memberships';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { RoleBadge } from '../../components/ui/StatusChip';
import { useToast } from '../../components/ui/Toast';
import { formatDate } from '../../lib/formatDate';
import type { VerifyResponse } from '../../types/api';
import {
  QrCode,
  Search,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCcw,
  Camera,
  CameraOff,
  UserCheck,
  ShieldAlert,
} from 'lucide-react';

export function VerifyMember() {
  const toast = useToast();
  const [queryInput, setQueryInput] = useState('');
  const [scannerActive, setScannerActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  const [verifyResult, setVerifyResult] = useState<VerifyResponse | null>(null);
  const [ambiguousCodes, setAmbiguousCodes] = useState<string[] | null>(null);

  const html5QrCodeRef = useRef<Html5Qrcode | null>(null);
  const scannerContainerId = 'reader-qr-view';

  const verifyMutation = useMutation({
    mutationFn: (search: string) => membershipsApi.verifyMember(search),
    onSuccess: (data) => {
      setVerifyResult(data);
      setAmbiguousCodes(null);
      if (data.valid) {
        toast.show(`Verified: ${data.member?.full_name}`, 'success');
      } else {
        toast.show(data.reason || 'Member verification failed', 'error');
      }
    },
    onError: (err: any) => {
      if (err.error?.code === 'AMBIGUOUS_QUERY' && err.error?.details?.member_codes) {
        setAmbiguousCodes(err.error.details.member_codes);
        setVerifyResult(null);
        toast.show('Multiple matches found. Select a member code below.', 'warning');
      } else {
        setVerifyResult({
          valid: false,
          reason: err.error?.message || err.message || 'Lookup failed',
        });
        setAmbiguousCodes(null);
      }
    },
  });

  const handleManualSearch = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = queryInput.trim();
    if (!q) {
      toast.show('Please enter a member code, email, or name to search.', 'warning');
      return;
    }
    verifyMutation.mutate(q);
  };

  const handleSelectAmbiguousCode = (code: string) => {
    setQueryInput(code);
    verifyMutation.mutate(code);
  };

  const handleReset = () => {
    setVerifyResult(null);
    setAmbiguousCodes(null);
    setQueryInput('');
  };

  const stopScanner = useCallback(() => {
    if (html5QrCodeRef.current && html5QrCodeRef.current.isScanning) {
      html5QrCodeRef.current
        .stop()
        .then(() => {
          setScannerActive(false);
        })
        .catch(() => {
          setScannerActive(false);
        });
    } else {
      setScannerActive(false);
    }
  }, []);

  // Camera QR Scanner Lifecycle
  useEffect(() => {
    if (scannerActive) {
      const qrScanner = new Html5Qrcode(scannerContainerId);
      html5QrCodeRef.current = qrScanner;

      qrScanner
        .start(
          { facingMode: 'environment' },
          {
            fps: 10,
            qrbox: { width: 250, height: 250 },
          },
          (decodedText) => {
            // Success scanning QR
            setQueryInput(decodedText);
            verifyMutation.mutate(decodedText);
            // Stop after one scan
            stopScanner();
          },
          () => {
            // Ignore scan frame misses
          }
        )
        .catch((err) => {
          setCameraError(err?.message || 'Unable to access camera');
          setScannerActive(false);
        });
    }

    return () => {
      if (html5QrCodeRef.current && html5QrCodeRef.current.isScanning) {
        html5QrCodeRef.current.stop().catch(() => {});
      }
    };
  }, [scannerActive, stopScanner, verifyMutation]);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="text-center max-w-xl mx-auto mb-8">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 mb-3">
          <UserCheck className="w-3.5 h-3.5" />
          Staff Verification Tool
        </div>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight">
          Member Check-in Scanner
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Fast verification for events, entry gates, and voting quorum.
        </p>
      </div>

      {/* Arm's Length Full Screen / Large Result Display */}
      {verifyResult && (
        <div
          role="region"
          aria-label="Verification Result"
          className={`mb-8 rounded-3xl p-8 sm:p-12 text-center shadow-2xl transition-all duration-300 animate-scale-up border-4 ${
            verifyResult.valid
              ? 'bg-emerald-50 text-emerald-700 border-emerald-600'
              : 'bg-rose-50 text-rose-700 border-rose-600'
          }`}
        >
          {verifyResult.valid ? (
            <div className="space-y-4">
              <CheckCircle2 className="w-24 h-24 sm:w-32 sm:h-32 mx-auto text-emerald-600 animate-bounce-short" />
              <div className="text-3xl sm:text-5xl font-black uppercase tracking-tight">
                ACCESS GRANTED
              </div>
              <div className="text-2xl sm:text-4xl font-extrabold text-emerald-700">
                {verifyResult.member?.full_name}
              </div>

              <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                <span className="font-mono text-base sm:text-lg bg-emerald-100 px-3 py-1 rounded-xl">
                  {verifyResult.member?.member_code}
                </span>
                {verifyResult.member?.role && (
                  <div className="bg-emerald-100 px-3 py-1 rounded-xl">
                    <RoleBadge role={verifyResult.member.role} />
                  </div>
                )}
                <span className="text-sm sm:text-base font-semibold bg-emerald-100 px-3 py-1 rounded-xl">
                  {verifyResult.member?.plan_name}
                </span>
              </div>

              <div className="text-sm sm:text-base text-emerald-600 font-medium pt-2">
                Valid until {formatDate(verifyResult.member?.valid_until)}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <XCircle className="w-24 h-24 sm:w-32 sm:h-32 mx-auto text-rose-600" />
              <div className="text-3xl sm:text-5xl font-black uppercase tracking-tight">
                ACCESS DENIED
              </div>
              <div className="text-xl sm:text-2xl font-bold text-rose-700">
                {verifyResult.reason || 'Invalid Member Credential'}
              </div>

              {verifyResult.member && (
                <div className="text-base text-rose-700">
                  {verifyResult.member.full_name} ({verifyResult.member.member_code})
                </div>
              )}
            </div>
          )}

          <div className="mt-8 pt-6 border-t border-slate-200">
            <Button
              size="lg"
              className="bg-white text-slate-950 hover:bg-slate-100 font-bold px-8 shadow-xl"
              onClick={handleReset}
            >
              <RotateCcw className="w-5 h-5 mr-2" />
              Scan Next Member
            </Button>
          </div>
        </div>
      )}

      {/* Disambiguation for Ambiguous Query (HTTP 409) */}
      {ambiguousCodes && ambiguousCodes.length > 0 && (
        <Card className="mb-8 border-amber-200 bg-amber-50">
          <CardHeader>
            <CardTitle className="text-amber-700 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" /> Multiple Matching Members Found
            </CardTitle>
            <CardDescription className="text-amber-700">
              Your search term matched multiple profiles. Select the exact member code to verify:
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2.5">
            {ambiguousCodes.map((code) => (
              <Button
                key={code}
                variant="outline"
                size="sm"
                className="font-mono border-amber-200 text-amber-700 hover:bg-amber-100"
                onClick={() => handleSelectAmbiguousCode(code)}
              >
                {code}
              </Button>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Input & Scanner Modes */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Manual Search */}
        <Card className="border-slate-200 bg-white">
          <CardHeader>
            <CardTitle className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Search className="w-5 h-5 text-emerald-600" />
              Manual Search
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              Type member code (e.g. SSA-2026-0001), email address, or name.
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleManualSearch} className="space-y-4">
              <Input
                label="Search Query"
                placeholder="SSA-2026-0001 or student@univ.edu"
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                autoFocus
              />

              <div className="flex gap-2">
                <Button
                  type="submit"
                  variant="primary"
                  className="flex-1"
                  disabled={verifyMutation.isPending}
                  isLoading={verifyMutation.isPending}
                >
                  <Search className="w-4 h-4 mr-1.5" />
                  Verify Member
                </Button>

                {(queryInput || verifyResult) && (
                  <Button type="button" variant="ghost" onClick={handleReset}>
                    Clear
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>

        {/* QR Camera Scanner */}
        <Card className="border-slate-200 bg-white flex flex-col">
          <CardHeader>
            <CardTitle className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <QrCode className="w-5 h-5 text-teal-600" />
              Camera QR Scanner
            </CardTitle>
            <CardDescription className="text-xs text-slate-500">
              Scan student's digital card directly using device camera.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1 flex flex-col justify-center items-center">
            {cameraError && (
              <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 shrink-0" />
                <span>{cameraError}</span>
              </div>
            )}

            <div
              id={scannerContainerId}
              className={`w-full max-w-[280px] rounded-xl overflow-hidden bg-slate-50 border border-slate-200 ${
                scannerActive ? 'block' : 'hidden'
              }`}
            />

            {!scannerActive ? (
              <div className="text-center py-6">
                <div className="w-16 h-16 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-500 mx-auto mb-3">
                  <Camera className="w-8 h-8" />
                </div>
                <Button
                  variant="outline"
                  onClick={() => {
                    setCameraError(null);
                    setScannerActive(true);
                  }}
                >
                  <Camera className="w-4 h-4 mr-2 text-teal-600" />
                  Start Camera Scanner
                </Button>
              </div>
            ) : (
              <Button
                variant="danger"
                size="sm"
                className="mt-4"
                onClick={stopScanner}
              >
                <CameraOff className="w-4 h-4 mr-1.5" />
                Stop Camera
              </Button>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
