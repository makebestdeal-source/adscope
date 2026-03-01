"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import {
  api, AdminStats, CrawlStatusResponse, CrawlChannelStatus,
  ScheduleOverview, ScheduleCategory, ScheduleItem,
  MediaSourceItem, CrawlLogItem,
} from "@/lib/api";
import { login as authLogin, getToken, getUser, logout as authLogout } from "@/lib/auth";

const CHANNEL_LABELS: Record<string, string> = {
  naver_search: "네이버 검색",
  naver_da: "네이버 DA",
  youtube_ads: "유튜브 광고",
  youtube_surf: "유튜브 서핑",
  google_gdn: "Google GDN",
  kakao_da: "카카오 DA",
  meta: "Meta",
};

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  recent: { bg: "bg-green-50", text: "text-green-700", dot: "bg-green-500" },
  today: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  stale: { bg: "bg-orange-50", text: "text-orange-700", dot: "bg-orange-500" },
  idle: { bg: "bg-gray-50", text: "text-gray-500", dot: "bg-gray-300" },
};

const STATUS_LABELS: Record<string, string> = {
  recent: "정상",
  today: "오늘 수집",
  stale: "오래됨",
  idle: "미수집",
};

const TABS = [
  { id: "overview", label: "수집 현황" },
  { id: "ad", label: "광고 수집" },
  { id: "social", label: "소셜 수집" },
  { id: "meta", label: "메타시그널" },
  { id: "media", label: "매체 관리" },
  { id: "crawl-log", label: "수집 로그" },
  { id: "schedule", label: "스케줄 타임라인" },
  { id: "users", label: "회원 관리" },
  { id: "payments", label: "결제 관리" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const CATEGORY_COLORS: Record<string, { border: string; bg: string; text: string; icon: string }> = {
  ad_collection: { border: "border-blue-200", bg: "bg-blue-50", text: "text-blue-700", icon: "text-blue-500" },
  social_collection: { border: "border-purple-200", bg: "bg-purple-50", text: "text-purple-700", icon: "text-purple-500" },
  meta_signals: { border: "border-amber-200", bg: "bg-amber-50", text: "text-amber-700", icon: "text-amber-500" },
};

const TIMELINE_COLORS: Record<string, string> = {
  social: "bg-purple-500",
  ad: "bg-blue-500",
  meta: "bg-amber-500",
};

export default function AdminPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [loginError, setLoginError] = useState("");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [crawlStatus, setCrawlStatus] = useState<CrawlStatusResponse | null>(null);
  const [schedule, setSchedule] = useState<ScheduleOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<Record<string, string>>({});
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [payments, setPayments] = useState<any[]>([]);
  const [paymentFilter, setPaymentFilter] = useState("all");
  const [usersLoading, setUsersLoading] = useState(false);
  const [paymentsLoading, setPaymentsLoading] = useState(false);

  useEffect(() => {
    const existingToken = getToken();
    const user = getUser();
    if (existingToken && user?.role === "admin") {
      setToken(existingToken);
      loadData(existingToken);
    }
  }, []);

  useEffect(() => {
    if (token) {
      intervalRef.current = setInterval(() => loadData(token), 30_000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [token]);

  const handleLogin = async () => {
    setLoginError("");
    try {
      const res = await authLogin(email, password);
      if (res.user.role !== "admin") {
        setLoginError("관리자 권한이 필요합니다.");
        authLogout();
        return;
      }
      setToken(res.access_token);
      setEmail("");
      setPassword("");
      await loadData(res.access_token);
    } catch {
      setLoginError("이메일 또는 비밀번호가 올바르지 않습니다.");
    }
  };

  const loadData = useCallback(async (t: string) => {
    setLoading(true);
    try {
      const [s, cs, sc] = await Promise.all([
        api.adminStats(t),
        api.adminCrawlStatus(t),
        api.adminScheduleOverview(t).catch(() => null),
      ]);
      setStats(s);
      setCrawlStatus(cs);
      if (sc) setSchedule(sc);
      setLastRefreshed(new Date());
    } catch (err) {
      // Only clear token on auth errors, not on server errors/timeouts
      if (err instanceof Error && err.message === "Session expired") {
        setToken(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const triggerAction = async (actionId: string, apiFn: (t: string) => Promise<{ status: string; message?: string }>) => {
    if (!token) return;
    setActionLoading(p => ({ ...p, [actionId]: true }));
    setActionMsg(p => ({ ...p, [actionId]: "" }));
    try {
      const res = await apiFn(token);
      setActionMsg(p => ({ ...p, [actionId]: res.message || "실행 완료" }));
      setTimeout(() => loadData(token), 2000);
    } catch {
      setActionMsg(p => ({ ...p, [actionId]: "실행 실패" }));
    } finally {
      setActionLoading(p => ({ ...p, [actionId]: false }));
    }
  };

  const ACTION_MAP: Record<string, (t: string) => Promise<{ status: string; message?: string }>> = {
    fast_crawl: api.adminStartCrawl,
    ai_enrich: (t) => api.adminAiEnrich(t).then(r => ({ ...r, message: "AI 보강 시작" })),
    campaign_rebuild: (t) => api.adminCollectCampaignRebuild(t).then(r => ({ ...r, message: "캠페인 리빌드 완료" })),
    brand_monitor: api.adminCollectSocial,
    social_stats: api.adminCollectSocial,
    smartstore: api.adminCollectSmartstore,
    traffic: api.adminCollectTraffic,
    activity: (t) => api.adminCollectActivity(t).then(r => ({ ...r, message: "활동 점수 계산 완료" })),
    meta_aggregate: (t) => api.adminCollectMetaAggregate(t).then(r => ({ ...r, message: "메타시그널 통합 완료" })),
  };

  const loadUsers = async () => {
    if (!token) return;
    setUsersLoading(true);
    try {
      const res = await api.adminListUsers(token);
      setUsers(res);
    } catch {
      // ignore
    } finally {
      setUsersLoading(false);
    }
  };

  const loadPayments = async () => {
    if (!token) return;
    setPaymentsLoading(true);
    try {
      const res = await api.adminListPayments(token, paymentFilter !== "all" ? paymentFilter : undefined);
      setPayments(res);
    } catch {
      // ignore
    } finally {
      setPaymentsLoading(false);
    }
  };

  useEffect(() => {
    if (token && activeTab === "users") loadUsers();
    if (token && activeTab === "payments") loadPayments();
  }, [activeTab, token]);

  useEffect(() => {
    if (token && activeTab === "payments") loadPayments();
  }, [paymentFilter]);

  const handleLogout = () => {
    setToken(null);
    setStats(null);
    setCrawlStatus(null);
    setSchedule(null);
    setActionMsg({});
    if (intervalRef.current) clearInterval(intervalRef.current);
    authLogout();
  };

  // ── 로그인 화면 ──
  if (!token) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center p-6">
        <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8 w-full max-w-sm">
          <div className="text-center mb-6">
            <div className="w-12 h-12 bg-slate-900 rounded-xl mx-auto mb-3 flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-6 h-6">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0110 0v4" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-gray-900">관리자 패널</h1>
            <p className="text-sm text-gray-500 mt-1">관리자 인증이 필요합니다</p>
          </div>
          <form onSubmit={(e) => { e.preventDefault(); handleLogin(); }}>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="이메일"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent" autoFocus />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="비밀번호"
              className="w-full mt-3 px-4 py-3 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent" />
            {loginError && <p className="text-red-500 text-xs mt-2">{loginError}</p>}
            <button type="submit" className="w-full mt-4 bg-slate-900 text-white py-3 rounded-lg text-sm font-medium hover:bg-slate-800 transition-colors">로그인</button>
          </form>
        </div>
      </div>
    );
  }

  // ── 관리 대시보드 ──
  return (
    <div className="p-6 lg:p-8 max-w-7xl">
      {/* 헤더 */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">수집 관리 센터</h1>
          <p className="text-sm text-gray-500 mt-1">
            데이터 수집 파이프라인 모니터링 및 제어
            {lastRefreshed && (
              <span className="ml-2 text-xs text-gray-400">
                (갱신: {lastRefreshed.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })} / 30초)
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => token && loadData(token)} disabled={loading}
            className="px-4 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50 flex items-center gap-2">
            {loading && <Spinner size={14} />}
            {loading ? "갱신 중..." : "새로고침"}
          </button>
          <button onClick={handleLogout}
            className="px-4 py-2 text-sm text-red-600 bg-white border border-red-200 rounded-lg hover:bg-red-50 transition-colors">
            로그아웃
          </button>
        </div>
      </div>

      {/* 탭 네비게이션 */}
      <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1">
        {TABS.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-2 px-3 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab.id
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── 탭 1: 수집 현황 ── */}
      {activeTab === "overview" && (
        <>
          {/* DB 통계 카드 */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
              <StatCard label="총 스냅샷" value={stats.total_snapshots} />
              <StatCard label="총 광고" value={stats.total_ads} />
              <StatCard label="광고주" value={stats.total_advertisers} />
              <StatCard label="키워드" value={stats.total_keywords} />
              <StatCard label="페르소나" value={stats.total_personas} />
            </div>
          )}

          {stats && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <InfoCard label="서버 시각 (KST)" value={formatKST(stats.server_time)} />
              <InfoCard label="최근 수집" value={stats.latest_crawl ? formatKST(stats.latest_crawl) : "없음"} />
              <InfoCard label="DB 크기" value={`${stats.db_size_mb} MB`} />
            </div>
          )}

          {/* 오늘 수집 요약 */}
          {crawlStatus && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-gray-700">오늘 수집 현황</h2>
                <div className="text-2xl font-bold text-adscope-600">{crawlStatus.summary.today_total_ads.toLocaleString()}건</div>
              </div>
              <div className="grid grid-cols-3 gap-4 text-center">
                <MiniStat label="총 광고주" value={crawlStatus.summary.total_advertisers} />
                <MiniStat label="총 광고" value={crawlStatus.summary.total_ads} />
                <MiniStat label="총 스냅샷" value={crawlStatus.summary.total_snapshots} />
              </div>
            </div>
          )}

          {/* 채널별 수집 상태 테이블 */}
          {crawlStatus && (crawlStatus?.channels || []).length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
              <div className="px-6 py-4 border-b border-gray-100">
                <h2 className="text-sm font-semibold text-gray-700">채널별 수집 상태</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
                      <th className="px-6 py-3">채널</th>
                      <th className="px-6 py-3">상태</th>
                      <th className="px-6 py-3 text-right">오늘</th>
                      <th className="px-6 py-3 text-right">총 스냅샷</th>
                      <th className="px-6 py-3">마지막 수집</th>
                      <th className="px-6 py-3 text-right">경과</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {(crawlStatus?.channels || []).map((ch) => (
                      <ChannelStatusRow key={ch.channel} channel={ch} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 채널 분포 */}
          {stats && Object.keys(stats?.by_channel || {}).length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">채널별 스냅샷 분포</h2>
              <div className="space-y-3">
                {Object.entries(stats?.by_channel || {}).sort(([, a], [, b]) => b - a).map(([ch, cnt]) => {
                  const max = Math.max(...Object.values(stats?.by_channel || {}));
                  const pct = max > 0 ? (cnt / max) * 100 : 0;
                  return (
                    <div key={ch}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-gray-600">{CHANNEL_LABELS[ch] || ch}</span>
                        <span className="text-xs font-bold text-gray-900">{cnt.toLocaleString()}</span>
                      </div>
                      <div className="w-full bg-gray-100 rounded-full h-2">
                        <div className="h-2 rounded-full bg-adscope-500 transition-all" style={{ width: `${Math.min(100, pct)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      {/* ── 탭 2: 광고 수집 ── */}
      {activeTab === "ad" && (
        <div className="space-y-6">
          <CategorySection
            title="광고 수집 파이프라인"
            description="접촉(네트워크 캡처) + 카탈로그(공개 라이브러리) 광고 데이터 수집"
            color="blue"
          >
            <CollectActionCard
              id="fast_crawl"
              title="병렬 크롤링 (fast_crawl)"
              description="7채널 병렬 수집: 네이버 검색/DA, 카카오 DA, Google GDN, YouTube Ads, Facebook, Instagram"
              schedule="수동 실행 또는 스케줄러"
              scheduleTime="평일 08:00~22:00 (페르소나 스케줄)"
              lastRun={schedule?.categories.find(c => c.id === "ad_collection")?.items[0]?.last_run}
              onTrigger={() => triggerAction("fast_crawl", ACTION_MAP.fast_crawl)}
              loading={!!actionLoading.fast_crawl}
              message={actionMsg.fast_crawl}
              buttonLabel="수집 시작"
              note="10분 제한, 완료 후 캠페인 자동 리빌드"
            />
            <CollectActionCard
              id="ai_enrich"
              title="AI 보강 (DeepSeek Vision)"
              description="광고 텍스트/이미지 분석으로 product_category, 광고 유형 자동 분류"
              schedule="매일 03:00 KST"
              scheduleTime="03:00"
              lastRun={null}
              onTrigger={() => triggerAction("ai_enrich", ACTION_MAP.ai_enrich)}
              loading={!!actionLoading.ai_enrich}
              message={actionMsg.ai_enrich}
              buttonLabel="AI 보강 실행"
            />
            <CollectActionCard
              id="campaign_rebuild"
              title="캠페인 / 광고비 리빌드"
              description="SpendEstimatorV2 기반 광고비 역추정 + 메타시그널 보정 (spend_multiplier 적용)"
              schedule="수집 완료 후 자동"
              scheduleTime="수집 직후"
              lastRun={null}
              onTrigger={() => triggerAction("campaign_rebuild", ACTION_MAP.campaign_rebuild)}
              loading={!!actionLoading.campaign_rebuild}
              message={actionMsg.campaign_rebuild}
              buttonLabel="리빌드 실행"
            />
          </CategorySection>
        </div>
      )}

      {/* ── 탭 3: 소셜 수집 ── */}
      {activeTab === "social" && (
        <div className="space-y-6">
          <CategorySection
            title="소셜 수집 파이프라인"
            description="브랜드 채널 콘텐츠 모니터링 + 소셜 통계 (인게이지먼트, 전월 대비 성장)"
            color="purple"
          >
            {schedule?.categories.find(c => c.id === "social_collection")?.items.map(item => (
              <CollectActionCard
                key={item.id}
                id={item.id}
                title={item.name}
                description={item.description}
                schedule={item.schedule}
                scheduleTime={item.schedule_time}
                lastRun={item.last_run}
                dataCount={item.data_count}
                onTrigger={() => triggerAction(item.id, ACTION_MAP[item.id] || api.adminCollectSocial)}
                loading={!!actionLoading[item.id]}
                message={actionMsg[item.id]}
                buttonLabel="수집 실행"
              />
            )) || (
              <>
                <CollectActionCard
                  id="brand_monitor"
                  title="브랜드 채널 모니터링"
                  description="YouTube/Instagram 채널 콘텐츠 수집 (영상, 게시물, 조회수, 좋아요)"
                  schedule="매일 02:00 KST"
                  scheduleTime="02:00"
                  lastRun={null}
                  onTrigger={() => triggerAction("brand_monitor", ACTION_MAP.brand_monitor)}
                  loading={!!actionLoading.brand_monitor}
                  message={actionMsg.brand_monitor}
                  buttonLabel="수집 실행"
                />
                <CollectActionCard
                  id="social_stats"
                  title="소셜 통계 (인게이지먼트)"
                  description="구독자/팔로워 수, 평균 좋아요/조회, 인게이지먼트율 계산"
                  schedule="매일 02:30 KST"
                  scheduleTime="02:30"
                  lastRun={null}
                  onTrigger={() => triggerAction("social_stats", ACTION_MAP.social_stats)}
                  loading={!!actionLoading.social_stats}
                  message={actionMsg.social_stats}
                  buttonLabel="수집 실행"
                />
              </>
            )}
          </CategorySection>

          {/* 소셜 통계 현황 요약 */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">소셜 데이터 현황</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MiniStat
                label="브랜드 콘텐츠"
                value={schedule?.categories.find(c => c.id === "social_collection")?.items[0]?.data_count || 0}
                suffix="건"
              />
              <MiniStat
                label="채널 통계"
                value={schedule?.categories.find(c => c.id === "social_collection")?.items[1]?.data_count || 0}
                suffix="건"
              />
              <div className="bg-gray-50 rounded-lg py-3 px-4">
                <p className="text-xs text-gray-500 mb-1">인게이지먼트 추적</p>
                <p className="text-sm font-medium text-purple-600">전월 대비 성장률 표시</p>
              </div>
              <div className="bg-gray-50 rounded-lg py-3 px-4">
                <p className="text-xs text-gray-500 mb-1">대상 플랫폼</p>
                <p className="text-sm font-medium text-gray-900">YouTube / Instagram</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 탭 4: 메타시그널 ── */}
      {activeTab === "meta" && (
        <div className="space-y-6">
          <CategorySection
            title="메타시그널 파이프라인"
            description="스마트스토어/트래픽/활동 지수 수집 → 통합 → spend_multiplier(0.7~1.5) 산출"
            color="amber"
          >
            {schedule?.categories.find(c => c.id === "meta_signals")?.items.map(item => (
              <CollectActionCard
                key={item.id}
                id={item.id}
                title={item.name}
                description={item.description}
                schedule={item.schedule}
                scheduleTime={item.schedule_time}
                lastRun={item.last_run}
                dataCount={item.data_count}
                onTrigger={() => triggerAction(item.id, ACTION_MAP[item.id] || (() => Promise.resolve({ status: "error", message: "not implemented" })))}
                loading={!!actionLoading[item.id]}
                message={actionMsg[item.id]}
                buttonLabel="실행"
              />
            )) || (
              <>
                <CollectActionCard id="smartstore" title="스마트스토어 신호" description="네이버 스마트스토어 리뷰/매출 메타데이터"
                  schedule="매일 04:00 KST" scheduleTime="04:00" lastRun={null}
                  onTrigger={() => triggerAction("smartstore", ACTION_MAP.smartstore)} loading={!!actionLoading.smartstore} message={actionMsg.smartstore} buttonLabel="실행" />
                <CollectActionCard id="traffic" title="트래픽 신호" description="네이버 DataLab + Google Trends 검색 지수"
                  schedule="매일 04:30 KST" scheduleTime="04:30" lastRun={null}
                  onTrigger={() => triggerAction("traffic", ACTION_MAP.traffic)} loading={!!actionLoading.traffic} message={actionMsg.traffic} buttonLabel="실행" />
                <CollectActionCard id="activity" title="활동 점수" description="크리에이티브/캠페인/채널 활동 복합 점수"
                  schedule="매일 05:00 KST" scheduleTime="05:00" lastRun={null}
                  onTrigger={() => triggerAction("activity", ACTION_MAP.activity)} loading={!!actionLoading.activity} message={actionMsg.activity} buttonLabel="실행" />
                <CollectActionCard id="meta_aggregate" title="메타시그널 통합" description="3개 신호 통합 → spend_multiplier 산출"
                  schedule="매일 05:30 KST" scheduleTime="05:30" lastRun={null}
                  onTrigger={() => triggerAction("meta_aggregate", ACTION_MAP.meta_aggregate)} loading={!!actionLoading.meta_aggregate} message={actionMsg.meta_aggregate} buttonLabel="실행" />
              </>
            )}
          </CategorySection>

          {/* 메타시그널 데이터 현황 */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">메타시그널 데이터 현황</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {schedule?.categories.find(c => c.id === "meta_signals")?.items.map(item => (
                <MiniStat key={item.id} label={item.name} value={item.data_count || 0} suffix="건" />
              )) || (
                <>
                  <MiniStat label="스마트스토어" value={0} suffix="건" />
                  <MiniStat label="트래픽" value={0} suffix="건" />
                  <MiniStat label="활동 점수" value={0} suffix="건" />
                  <MiniStat label="통합 신호" value={0} suffix="건" />
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── 탭 6: 회원 관리 ── */}
      {activeTab === "users" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">회원 목록</h2>
            <button
              onClick={loadUsers}
              disabled={usersLoading}
              className="px-3 py-1.5 text-xs bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              {usersLoading && <Spinner size={12} />}
              새로고침
            </button>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
                    <th className="px-3 py-3">이메일</th>
                    <th className="px-3 py-3">이름</th>
                    <th className="px-3 py-3">회사명</th>
                    <th className="px-3 py-3">유형</th>
                    <th className="px-3 py-3 text-center">자료조회</th>
                    <th className="px-3 py-3 text-center">다운로드</th>
                    <th className="px-3 py-3 text-center">관리</th>
                    <th className="px-3 py-3">플랜</th>
                    <th className="px-3 py-3">만료일</th>
                    <th className="px-3 py-3">상태</th>
                    <th className="px-3 py-3 text-right">작업</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {usersLoading ? (
                    <tr>
                      <td colSpan={11} className="px-4 py-8 text-center text-sm text-gray-400">
                        <Spinner size={16} />
                        <span className="ml-2">로딩 중...</span>
                      </td>
                    </tr>
                  ) : users.length === 0 ? (
                    <tr>
                      <td colSpan={11} className="px-4 py-8 text-center text-sm text-gray-400">회원 없음</td>
                    </tr>
                  ) : (
                    users.map((u: any) => {
                      const expiresAt = u.plan_expires_at ? new Date(u.plan_expires_at) : null;
                      const now = new Date();
                      const daysLeft = expiresAt ? Math.ceil((expiresAt.getTime() - now.getTime()) / 86400000) : null;
                      const expired = daysLeft !== null && daysLeft < 0;
                      const isAdmin = u.role === "admin";
                      const canView = u.is_active;
                      const canDownload = u.payment_confirmed === true;
                      const canManage = isAdmin;

                      // User type badge
                      const userType = isAdmin ? "관리자" :
                        u.plan === "full" ? "유료(Full)" :
                        u.plan === "lite" ? "유료(Lite)" : "무료체험";
                      const typeBadgeClass = isAdmin ? "bg-purple-100 text-purple-700" :
                        u.plan === "full" ? "bg-adscope-100 text-adscope-700" :
                        u.plan === "lite" ? "bg-blue-50 text-blue-600" :
                        "bg-gray-100 text-gray-500";

                      const handlePermChange = async (params: { can_download?: boolean; can_manage?: boolean; plan?: string; is_active?: boolean }) => {
                        if (!token) return;
                        try {
                          await api.adminUpdatePermissions(u.id, params, token);
                          await loadUsers();
                        } catch {
                          alert("권한 변경 실패");
                        }
                      };

                      return (
                        <tr key={u.id} className="hover:bg-gray-50">
                          <td className="px-3 py-3 text-xs text-gray-900">{u.email}</td>
                          <td className="px-3 py-3 text-xs text-gray-700">{u.name || "-"}</td>
                          <td className="px-3 py-3 text-xs text-gray-700">{u.company_name || "-"}</td>
                          <td className="px-3 py-3">
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${typeBadgeClass}`}>
                              {userType}
                            </span>
                          </td>
                          {/* 자료조회 */}
                          <td className="px-3 py-3 text-center">
                            <input
                              type="checkbox"
                              checked={canView}
                              onChange={(e) => handlePermChange({ is_active: e.target.checked })}
                              className="w-4 h-4 text-blue-600 rounded border-gray-300 cursor-pointer"
                            />
                          </td>
                          {/* 다운로드 */}
                          <td className="px-3 py-3 text-center">
                            <input
                              type="checkbox"
                              checked={canDownload}
                              onChange={(e) => handlePermChange({ can_download: e.target.checked })}
                              className="w-4 h-4 text-blue-600 rounded border-gray-300 cursor-pointer"
                            />
                          </td>
                          {/* 관리 */}
                          <td className="px-3 py-3 text-center">
                            <input
                              type="checkbox"
                              checked={canManage}
                              disabled={isAdmin && u.email === getUser()?.email}
                              onChange={(e) => {
                                if (!e.target.checked && isAdmin) {
                                  if (!confirm(`${u.email}의 관리자 권한을 해제하겠습니까?`)) return;
                                }
                                handlePermChange({ can_manage: e.target.checked });
                              }}
                              className="w-4 h-4 text-blue-600 rounded border-gray-300 cursor-pointer disabled:opacity-50"
                            />
                          </td>
                          {/* 플랜 */}
                          <td className="px-3 py-3">
                            <select
                              value={u.plan || "free"}
                              onChange={(e) => {
                                const newPlan = e.target.value === "free" ? undefined : e.target.value;
                                if (newPlan) handlePermChange({ plan: newPlan });
                              }}
                              className="text-xs border border-gray-200 rounded px-1.5 py-1 bg-white cursor-pointer"
                            >
                              <option value="free">무료체험</option>
                              <option value="lite">Lite</option>
                              <option value="full">Full</option>
                            </select>
                          </td>
                          <td className="px-3 py-3 text-xs">
                            {expiresAt ? (
                              <span className={expired ? "text-red-600 font-medium" : "text-gray-600"}>
                                {expiresAt.toLocaleDateString("ko-KR")}
                                {daysLeft !== null && (
                                  <span className={`ml-1 ${expired ? "text-red-500" : "text-gray-400"}`}>
                                    ({expired ? `${Math.abs(daysLeft)}일 초과` : `${daysLeft}일 남음`})
                                  </span>
                                )}
                              </span>
                            ) : "-"}
                          </td>
                          <td className="px-3 py-3">
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                              u.is_active ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"
                            }`}>
                              {u.is_active ? "활성" : "비활성"}
                            </span>
                          </td>
                          <td className="px-3 py-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <button
                                onClick={async () => {
                                  if (!token) return;
                                  try {
                                    await api.adminExtendUser(u.id, 30, token);
                                    await loadUsers();
                                  } catch {
                                    alert("연장 실패");
                                  }
                                }}
                                className="px-2.5 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                              >
                                30일 연장
                              </button>
                              {!isAdmin && (
                                <button
                                  onClick={async () => {
                                    if (!token || !confirm(`${u.email} 계정을 비활성화하겠습니까?`)) return;
                                    try {
                                      await api.adminDeactivateUser(u.id, token);
                                      await loadUsers();
                                    } catch {
                                      alert("비활성화 실패");
                                    }
                                  }}
                                  className="px-2.5 py-1 text-xs bg-red-100 text-red-600 rounded hover:bg-red-200 transition-colors"
                                >
                                  비활성화
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── 탭 7: 결제 관리 ── */}
      {activeTab === "payments" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <h2 className="text-sm font-semibold text-gray-700">결제 목록</h2>
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                {["all", "pending", "paid", "activated", "failed", "refunded"].map(s => (
                  <button
                    key={s}
                    onClick={() => setPaymentFilter(s)}
                    className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                      paymentFilter === s
                        ? "bg-slate-800 text-white"
                        : "bg-white border border-gray-300 text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    {{
                      all: "전체",
                      pending: "대기",
                      paid: "결제완료",
                      activated: "승인됨",
                      failed: "실패",
                      refunded: "환불",
                    }[s]}
                  </button>
                ))}
              </div>
              <button
                onClick={loadPayments}
                disabled={paymentsLoading}
                className="px-3 py-1.5 text-xs bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {paymentsLoading && <Spinner size={12} />}
                새로고침
              </button>
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase tracking-wider">
                    <th className="px-4 py-3">주문번호</th>
                    <th className="px-4 py-3">이메일</th>
                    <th className="px-4 py-3">플랜</th>
                    <th className="px-4 py-3 text-right">금액</th>
                    <th className="px-4 py-3">상태</th>
                    <th className="px-4 py-3">결제일</th>
                    <th className="px-4 py-3 text-right">작업</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {paymentsLoading ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-sm text-gray-400">
                        <Spinner size={16} />
                        <span className="ml-2">로딩 중...</span>
                      </td>
                    </tr>
                  ) : payments.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-sm text-gray-400">결제 없음</td>
                    </tr>
                  ) : (
                    payments.map((p: any) => {
                      const statusBadge: Record<string, string> = {
                        pending: "bg-gray-100 text-gray-600",
                        paid: "bg-yellow-100 text-yellow-700",
                        activated: "bg-green-100 text-green-700",
                        failed: "bg-red-100 text-red-600",
                        refunded: "bg-gray-100 text-gray-500",
                      };
                      const statusLabel: Record<string, string> = {
                        pending: "대기",
                        paid: "결제완료",
                        activated: "승인됨",
                        failed: "실패",
                        refunded: "환불",
                      };
                      return (
                        <tr key={p.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-xs font-mono text-gray-700">{p.merchant_uid || p.id}</td>
                          <td className="px-4 py-3 text-xs text-gray-700">{p.user_email || p.email || "-"}</td>
                          <td className="px-4 py-3 text-xs text-gray-600">{p.plan || "-"} {p.plan_period ? `/ ${p.plan_period}` : ""}</td>
                          <td className="px-4 py-3 text-xs text-right font-medium text-gray-900">
                            {p.amount != null ? `${Number(p.amount).toLocaleString("ko-KR")}원` : "-"}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusBadge[p.status] || "bg-gray-100 text-gray-500"}`}>
                              {statusLabel[p.status] || p.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500">
                            {p.paid_at ? formatKST(p.paid_at) : "-"}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {p.status === "paid" && (
                              <div className="flex items-center justify-end gap-2">
                                <button
                                  onClick={async () => {
                                    if (!token) return;
                                    try {
                                      await api.adminActivatePayment(p.id, token);
                                      await loadPayments();
                                    } catch {
                                      alert("승인 실패");
                                    }
                                  }}
                                  className="px-2.5 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
                                >
                                  승인
                                </button>
                                <button
                                  onClick={async () => {
                                    if (!token || !confirm("이 결제를 거절하겠습니까?")) return;
                                    try {
                                      await api.adminRejectPayment(p.id, token);
                                      await loadPayments();
                                    } catch {
                                      alert("거절 실패");
                                    }
                                  }}
                                  className="px-2.5 py-1 text-xs bg-red-100 text-red-600 rounded hover:bg-red-200 transition-colors"
                                >
                                  거절
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── 탭: 매체 관리 ── */}
      {activeTab === "media" && <MediaSourcesPanel token={token} />}

      {/* ── 탭: 수집 로그 ── */}
      {activeTab === "crawl-log" && <CrawlLogPanel token={token} />}

      {/* ── 탭 5: 스케줄 타임라인 ── */}
      {activeTab === "schedule" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">일일 수집 스케줄 타임라인</h2>
            <p className="text-xs text-gray-400 mb-6">모든 시간은 KST (Asia/Seoul) 기준. 스케줄러 프로세스 실행 필수.</p>

            <div className="relative">
              {/* 타임라인 세로선 */}
              <div className="absolute left-[72px] top-0 bottom-0 w-0.5 bg-gray-200" />

              <div className="space-y-0">
                {(schedule?.timeline || DEFAULT_TIMELINE).map((item, i) => (
                  <div key={i} className="flex items-center gap-4 py-3 group hover:bg-gray-50 rounded-lg px-2 -mx-2">
                    <div className="w-16 text-right">
                      <span className="text-sm font-mono font-semibold text-gray-700">{item.time}</span>
                    </div>
                    <div className="relative z-10">
                      <div className={`w-3 h-3 rounded-full border-2 border-white ${TIMELINE_COLORS[item.category] || "bg-gray-400"}`} />
                    </div>
                    <div className="flex-1">
                      <span className="text-sm text-gray-800">{item.label}</span>
                      <span className={`ml-2 text-[10px] font-medium px-1.5 py-0.5 rounded ${
                        item.category === "social" ? "bg-purple-100 text-purple-600" :
                        item.category === "ad" ? "bg-blue-100 text-blue-600" :
                        "bg-amber-100 text-amber-600"
                      }`}>
                        {item.category === "social" ? "소셜" : item.category === "ad" ? "광고" : "메타시그널"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 카테고리 범례 */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">카테고리별 수집 순서</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-purple-500" />
                  <span className="text-sm font-medium text-gray-800">Phase 1: 소셜 수집</span>
                </div>
                <p className="text-xs text-gray-500 pl-5">02:00~02:30 / 브랜드 채널 + 인게이지먼트</p>
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-blue-500" />
                  <span className="text-sm font-medium text-gray-800">Phase 2: 광고 보강</span>
                </div>
                <p className="text-xs text-gray-500 pl-5">03:00 / AI 텍스트+이미지 분류</p>
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-amber-500" />
                  <span className="text-sm font-medium text-gray-800">Phase 3: 메타시그널</span>
                </div>
                <p className="text-xs text-gray-500 pl-5">04:00~05:30 / 스마트스토어 → 트래픽 → 활동 → 통합</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-gray-100">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-blue-500" />
                <span className="text-sm font-medium text-gray-800">일과: 광고 접촉 수집</span>
              </div>
              <p className="text-xs text-gray-500 pl-5">08:00~22:00 / 페르소나 스케줄 (평일/주말 구분)</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 기본 타임라인 (API 응답 없을 때) ──
const DEFAULT_TIMELINE = [
  { time: "02:00", label: "브랜드 채널 모니터링", category: "social" },
  { time: "02:30", label: "소셜 통계 (인게이지먼트)", category: "social" },
  { time: "03:00", label: "AI 보강", category: "ad" },
  { time: "04:00", label: "스마트스토어 신호", category: "meta" },
  { time: "04:30", label: "트래픽 신호", category: "meta" },
  { time: "05:00", label: "활동 점수", category: "meta" },
  { time: "05:30", label: "메타시그널 통합", category: "meta" },
  { time: "08:00-22:00", label: "광고 접촉 수집 (페르소나 스케줄)", category: "ad" },
];

// ── 컴포넌트 ──

function CategorySection({ title, description, color, children }: {
  title: string;
  description: string;
  color: "blue" | "purple" | "amber";
  children: React.ReactNode;
}) {
  const colors = {
    blue: "border-l-blue-500",
    purple: "border-l-purple-500",
    amber: "border-l-amber-500",
  };
  return (
    <div className={`bg-white rounded-xl border border-gray-200 border-l-4 ${colors[color]} overflow-hidden`}>
      <div className="px-6 py-4 border-b border-gray-100">
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
        <p className="text-xs text-gray-500 mt-0.5">{description}</p>
      </div>
      <div className="divide-y divide-gray-100">
        {children}
      </div>
    </div>
  );
}

function CollectActionCard({ id, title, description, schedule, scheduleTime, lastRun, dataCount, onTrigger, loading, message, buttonLabel, note }: {
  id: string;
  title: string;
  description: string;
  schedule: string;
  scheduleTime: string;
  lastRun: string | null | undefined;
  dataCount?: number;
  onTrigger: () => void;
  loading: boolean;
  message?: string;
  buttonLabel: string;
  note?: string;
}) {
  const lastRunDisplay = lastRun ? formatKST(lastRun) : "미실행";
  const isStale = !lastRun;

  return (
    <div className="px-6 py-4 hover:bg-gray-50 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
            <span className="text-[10px] font-mono px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">{scheduleTime}</span>
          </div>
          <p className="text-xs text-gray-500 mb-2">{description}</p>
          <div className="flex items-center gap-4 text-xs">
            <span className="text-gray-400">
              스케줄: <span className="text-gray-600">{schedule}</span>
            </span>
            <span className={isStale ? "text-orange-500" : "text-gray-400"}>
              마지막: <span className={isStale ? "text-orange-600 font-medium" : "text-gray-600"}>{lastRunDisplay}</span>
            </span>
            {dataCount !== undefined && (
              <span className="text-gray-400">
                데이터: <span className="text-gray-600 font-medium">{dataCount.toLocaleString()}건</span>
              </span>
            )}
          </div>
          {note && <p className="text-[11px] text-gray-400 mt-1">{note}</p>}
          {message && (
            <p className={`text-xs mt-1.5 ${message.includes("실패") ? "text-red-600" : "text-green-600"}`}>{message}</p>
          )}
        </div>
        <button
          onClick={onTrigger}
          disabled={loading}
          className="flex-shrink-0 px-4 py-2 bg-adscope-600 text-white text-xs font-medium rounded-lg hover:bg-adscope-700 transition-colors disabled:opacity-50 flex items-center gap-1.5"
        >
          {loading && <Spinner size={12} />}
          {buttonLabel}
        </button>
      </div>
    </div>
  );
}

function ChannelStatusRow({ channel }: { channel: CrawlChannelStatus }) {
  const colors = STATUS_COLORS[channel.status] || STATUS_COLORS.idle;
  const label = STATUS_LABELS[channel.status] || channel.status;
  const elapsedText = (() => {
    if (channel.minutes_ago === null) return "-";
    if (channel.minutes_ago < 1) return "방금 전";
    if (channel.minutes_ago < 60) return `${channel.minutes_ago}분 전`;
    const hours = Math.floor(channel.minutes_ago / 60);
    if (hours < 24) return `${hours}시간 전`;
    return `${Math.floor(hours / 24)}일 전`;
  })();

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-6 py-3 font-medium text-gray-900">
        {CHANNEL_LABELS[channel.channel] || channel.channel}
        <span className="ml-1 text-[10px] text-gray-400">{channel.channel}</span>
      </td>
      <td className="px-6 py-3">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
          {label}
        </span>
      </td>
      <td className="px-6 py-3 text-right font-semibold text-gray-900 tabular-nums">{channel.today_ads.toLocaleString()}</td>
      <td className="px-6 py-3 text-right text-gray-600 tabular-nums">{channel.total_snapshots.toLocaleString()}</td>
      <td className="px-6 py-3 text-gray-500 text-xs">{channel.last_crawl_kst ? formatKST(channel.last_crawl_kst) : "-"}</td>
      <td className="px-6 py-3 text-right text-xs text-gray-500">{elapsedText}</td>
    </tr>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value.toLocaleString()}</p>
    </div>
  );
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-sm font-medium text-gray-900">{value}</p>
    </div>
  );
}

function MiniStat({ label, value, suffix }: { label: string; value: number; suffix?: string }) {
  return (
    <div className="bg-gray-50 rounded-lg py-3 px-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-lg font-bold text-gray-900">{value.toLocaleString()}{suffix && <span className="text-xs font-normal text-gray-500 ml-0.5">{suffix}</span>}</p>
    </div>
  );
}

function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg className="animate-spin" width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function formatKST(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}


// ── 매체 관리 패널 ──
function MediaSourcesPanel({ token }: { token: string | null }) {
  const [sources, setSources] = useState<MediaSourceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", url: "", connector_type: "rss", weight: 1.0, schedule_interval: 60 });
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try { setSources(await api.adminListMediaSources()); } catch { /* ignore */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      await api.adminCreateMediaSource(form);
      setShowForm(false);
      setForm({ name: "", url: "", connector_type: "rss", weight: 1.0, schedule_interval: 60 });
      setMsg("매체가 등록되었습니다");
      load();
    } catch (e: any) {
      setMsg("등록 실패: " + (e.message || ""));
    }
  };

  const toggleActive = async (id: number, current: boolean) => {
    try {
      await api.adminUpdateMediaSource(id, { is_active: !current });
      load();
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">등록 매체 목록</h2>
        <div className="flex gap-2">
          <button onClick={() => setShowForm(!showForm)} className="px-3 py-1.5 text-xs bg-adscope-600 text-white rounded-lg hover:bg-adscope-700">
            {showForm ? "취소" : "+ 매체 추가"}
          </button>
          <button onClick={load} disabled={loading} className="px-3 py-1.5 text-xs bg-white border rounded-lg hover:bg-gray-50 disabled:opacity-50">
            새로고침
          </button>
        </div>
      </div>

      {msg && <p className={`text-xs ${msg.includes("실패") ? "text-red-600" : "text-green-600"}`}>{msg}</p>}

      {showForm && (
        <div className="bg-white rounded-xl border p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input placeholder="매체명" value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="px-3 py-2 text-sm border rounded-lg" />
            <input placeholder="URL" value={form.url} onChange={e => setForm({...form, url: e.target.value})} className="px-3 py-2 text-sm border rounded-lg" />
            <select value={form.connector_type} onChange={e => setForm({...form, connector_type: e.target.value})} className="px-3 py-2 text-sm border rounded-lg">
              <option value="rss">RSS</option>
              <option value="api_youtube">YouTube API</option>
              <option value="html_list_detail">HTML (셀렉터)</option>
            </select>
            <input type="number" placeholder="가중치" value={form.weight} onChange={e => setForm({...form, weight: Number(e.target.value)})} className="px-3 py-2 text-sm border rounded-lg" />
          </div>
          <button onClick={handleCreate} className="px-4 py-2 text-xs bg-adscope-600 text-white rounded-lg hover:bg-adscope-700">등록</button>
        </div>
      )}

      <div className="bg-white rounded-xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase">
              <th className="px-4 py-3">매체명</th>
              <th className="px-4 py-3">타입</th>
              <th className="px-4 py-3 text-right">가중치</th>
              <th className="px-4 py-3 text-right">수집 건수</th>
              <th className="px-4 py-3">마지막 수집</th>
              <th className="px-4 py-3 text-right">에러율</th>
              <th className="px-4 py-3 text-center">활성</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sources.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-gray-400">등록된 매체 없음</td></tr>
            ) : sources.map(s => (
              <tr key={s.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <div className="font-medium text-gray-900 text-xs">{s.name}</div>
                  <div className="text-[10px] text-gray-400 truncate max-w-[200px]">{s.url}</div>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    s.connector_type === "rss" ? "bg-blue-100 text-blue-700" :
                    s.connector_type === "api_youtube" ? "bg-red-100 text-red-700" :
                    "bg-green-100 text-green-700"
                  }`}>{s.connector_type}</span>
                </td>
                <td className="px-4 py-3 text-right text-xs">{s.weight}</td>
                <td className="px-4 py-3 text-right text-xs font-medium">{s.mention_count.toLocaleString()}</td>
                <td className="px-4 py-3 text-xs text-gray-500">{s.last_crawl_at ? formatKST(s.last_crawl_at) : "-"}</td>
                <td className="px-4 py-3 text-right text-xs">
                  <span className={s.error_rate > 0.3 ? "text-red-600 font-medium" : "text-gray-500"}>
                    {(s.error_rate * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-center">
                  <button onClick={() => toggleActive(s.id, s.is_active)} className={`w-10 h-5 rounded-full transition-colors ${s.is_active ? "bg-green-500" : "bg-gray-300"}`}>
                    <div className={`w-4 h-4 bg-white rounded-full shadow transition-transform ${s.is_active ? "translate-x-5" : "translate-x-0.5"}`} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ── 수집 로그 패널 ──
function CrawlLogPanel({ token }: { token: string | null }) {
  const [logs, setLogs] = useState<CrawlLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [crawling, setCrawling] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try { setLogs(await api.adminGetCrawlLog()); } catch { /* ignore */ }
    setLoading(false);
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const handleCrawl = async () => {
    setCrawling(true);
    setMsg("");
    try {
      const res = await api.adminTriggerLIICrawl();
      setMsg(`수집 완료: ${res.stats?.sources_processed || 0}개 매체, ${res.stats?.mentions_created || 0}건 생성`);
      load();
    } catch (e: any) {
      setMsg("수집 실패: " + (e.message || ""));
    }
    setCrawling(false);
  };

  const handleCalcScores = async () => {
    setScoring(true);
    setMsg("");
    try {
      const res = await api.adminTriggerLIICalcScores();
      setMsg(`점수 계산 완료: ${res.stats?.processed || 0}건`);
    } catch (e: any) {
      setMsg("계산 실패: " + (e.message || ""));
    }
    setScoring(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-sm font-semibold text-gray-700">매체 수집 로그</h2>
        <div className="flex gap-2">
          <button onClick={handleCrawl} disabled={crawling} className="px-3 py-1.5 text-xs bg-adscope-600 text-white rounded-lg hover:bg-adscope-700 disabled:opacity-50 flex items-center gap-1.5">
            {crawling && <Spinner size={12} />}
            지금 수집
          </button>
          <button onClick={handleCalcScores} disabled={scoring} className="px-3 py-1.5 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-1.5">
            {scoring && <Spinner size={12} />}
            점수 계산
          </button>
          <button onClick={load} disabled={loading} className="px-3 py-1.5 text-xs bg-white border rounded-lg hover:bg-gray-50 disabled:opacity-50">
            새로고침
          </button>
        </div>
      </div>

      {msg && <p className={`text-xs ${msg.includes("실패") ? "text-red-600" : "text-green-600"}`}>{msg}</p>}

      <div className="bg-white rounded-xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs text-gray-500 uppercase">
              <th className="px-4 py-3">매체명</th>
              <th className="px-4 py-3">타입</th>
              <th className="px-4 py-3">상태</th>
              <th className="px-4 py-3">마지막 수집</th>
              <th className="px-4 py-3 text-right">에러 수</th>
              <th className="px-4 py-3 text-right">에러율</th>
              <th className="px-4 py-3 text-right">수집 건수</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {logs.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-gray-400">로그 없음</td></tr>
            ) : logs.map(l => (
              <tr key={l.media_source_id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-xs font-medium text-gray-900">{l.media_source_name}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    l.connector_type === "rss" ? "bg-blue-100 text-blue-700" :
                    l.connector_type === "api_youtube" ? "bg-red-100 text-red-700" :
                    "bg-green-100 text-green-700"
                  }`}>{l.connector_type}</span>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${l.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                    {l.is_active ? "활성" : "비활성"}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">{l.last_crawl_at ? formatKST(l.last_crawl_at) : "미실행"}</td>
                <td className="px-4 py-3 text-right text-xs">{l.error_count}</td>
                <td className="px-4 py-3 text-right text-xs">
                  <span className={l.error_rate > 0.3 ? "text-red-600 font-medium" : "text-gray-500"}>
                    {(l.error_rate * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-xs font-medium">{l.mention_count.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
