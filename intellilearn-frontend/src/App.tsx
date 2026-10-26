import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import AppShell from "./components/AppShell";

import {

  ArrowLeft,

  ArrowRight,

  Atom,

  BookOpen,

  Brain,

  ChevronRight,

  CircleHelp,

  Clock3,

  FlaskConical,


  LayoutDashboard,

  FileCheck2,

  Upload,

  Lightbulb,

  MessageSquare,

  NotebookPen,

  Send,

  Target,

  Timer,

  X,

} from "lucide-react";

import ReactMarkdown from "react-markdown";

import remarkGfm from "remark-gfm";

import remarkMath from "remark-math";

import rehypeKatex from "rehype-katex";

const API = import.meta.env.VITE_API_URL || "https://adaptivelearning-e6ebgzf2gvegb0df.centralindia-01.azurewebsites.net"

type Page =

  | "dashboard"

  | "test-menu"

  | "exam"

  | "subjects"

  | "topics"

  | "configure"

  | "results"

  | "tutor"

  | "upload";

const routeByPage: Record<Page, string> = {
  dashboard: "/dashboard",
  "test-menu": "/test-menu",
  exam: "/exam",
  subjects: "/subjects",
  topics: "/topics",
  configure: "/configure",
  results: "/results",
  tutor: "/chat",
  upload: "/upload",
};

function pageFromPath(pathname: string): Page {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  const found = Object.entries(routeByPage).find(([, path]) => path === normalized);
  return (found?.[0] as Page | undefined) || "dashboard";
}

type Question = {

  id: number;

  question: string;

  options: string[];

  correct_answer?: string;

  explanation?: string;

  subject?: string;

  topic?: string;

  difficulty?: string;

};

type Source = {

  chunk_id: number;

  filename: string;

  page_number: number | null;

  content: string;

  similarity: number;

};

type ChatConversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  created_at: string;
};

type Subject = {

  name: string;

  topics: string[];

  color: string;

};

const subjectColor = (name: string) => {

  const colors: Record<string, string> = {

    Chemistry: "green",

    Mathematics: "purple",

    Physics: "blue",

    Biology: "green",

    "Computer Science": "blue",

  };

  return colors[name] || "purple";

};

async function api<T>(path: string, body?: unknown): Promise<T> {

  const token = localStorage.getItem("intellilearn_access_token");

  const headers: Record<string, string> = {};

  if (body !== undefined) headers["Content-Type"] = "application/json";

  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API}${path}`, {

    method: body === undefined ? "GET" : "POST",

    headers,

    body: body === undefined ? undefined : JSON.stringify(body),

  });

  const data = await response

    .json()

    .catch(() => ({ detail: `Request failed (${response.status})` }));

  if (!response.ok)

    throw new Error(

      data.detail || data.message || `Request failed (${response.status})`

    );

  return data as T;

}

const questionCountByDuration: Record<number, number> = {
  10: 5,
  15: 8,
  30: 16,
  60: 35,
  90: 65,
  180: 100,
};

type DashboardSummary = {
  average_accuracy: number;
  tests_completed: number;
  topics_practiced: number;
  study_time_minutes: number;
};

type TestHistoryItem = {
  session_id: string;
  subject: string;
  topic: string | null;
  score: number;
  total_questions: number;
  accuracy_percent: number;
  completed_at: string;
};

function App() {

  const navigate = useNavigate();
  const location = useLocation();
  const [authToken, setAuthToken] = useState(

    () => localStorage.getItem("intellilearn_access_token") || ""

  );

  const [authUser, setAuthUser] = useState<{

    full_name: string;

    email: string;

  } | null>(() => {

    try {

      return JSON.parse(localStorage.getItem("intellilearn_user") || "null");

    } catch {

      return null;

    }

  });

  const [page, setPage] = useState<Page>(() => pageFromPath(window.location.pathname));

  useEffect(() => {
    setPage(pageFromPath(location.pathname));
  }, [location.pathname]);

  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [dashboardSummary, setDashboardSummary] = useState<DashboardSummary | null>(null);
  const [testHistory, setTestHistory] = useState<TestHistoryItem[]>([]);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [testStartedAt, setTestStartedAt] = useState<number | null>(null);

  const [subject, setSubject] = useState("");

  const [topic, setTopic] = useState("");

  const [duration, setDuration] = useState(15);

  const [difficulty, setDifficulty] = useState("Recommended");

  const [questions, setQuestions] = useState<Question[]>([]);

  const [index, setIndex] = useState(0);

  const [answers, setAnswers] = useState<Record<number, string>>({});

  const [remaining, setRemaining] = useState(3600);

  const [result, setResult] = useState(false);

  const [busy, setBusy] = useState(false);

  const [notice, setNotice] = useState("");

  const [tutorInput, setTutorInput] = useState("");

  const [tutorAnswer, setTutorAnswer] = useState("");

  const [sources, setSources] = useState<Source[]>([]);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);

  const [selectedPdf, setSelectedPdf] = useState<File | null>(null);

  const [uploadingPdf, setUploadingPdf] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!authToken || page !== "dashboard") return;

    async function loadDashboard() {
      setDashboardLoading(true);
      try {
        const [summary, history] = await Promise.all([
          api<DashboardSummary>("/dashboard/summary"),
          api<{ tests: TestHistoryItem[] }>("/dashboard/history"),
        ]);
        if (!cancelled) {
          setDashboardSummary(summary);
          setTestHistory(history.tests || []);
        }
      } catch (error) {
        if (!cancelled) {
          setNotice(error instanceof Error ? error.message : "Could not load test history.");
        }
      } finally {
        if (!cancelled) setDashboardLoading(false);
      }
    }

    loadDashboard();
    return () => { cancelled = true; };
  }, [authToken, page]);

  useEffect(() => {

    let cancelled = false;

    if (!authToken || page !== "subjects") return;

    async function loadSubjects() {

      try {

        const data = await api<{

          subjects?: { name: string; topics: string[] }[];

        }>("/topics");

        if (cancelled) return;

        const loadedSubjects: Subject[] = (data.subjects || []).map((item) => ({

          name: item.name,

          topics: item.topics || [],

          color: subjectColor(item.name),

        }));

        setSubjects(loadedSubjects);

        if (loadedSubjects.length > 0) {

          const firstSubject = loadedSubjects[0];

          setSubject((current) =>

            loadedSubjects.some((item) => item.name === current)

              ? current

              : firstSubject.name

          );

          setTopic((current) => current || firstSubject.topics[0] || "");

        }

      } catch (error) {

        if (!cancelled) {

          setNotice(

            `Could not load subjects and topics from the backend: ${error instanceof Error ? error.message : String(error)

            }`

          );

        }

      }

    }

    loadSubjects();

    return () => {

      cancelled = true;

    };

  }, [authToken, page]);

  const current = questions[index];

  const answered = Object.keys(answers).length;

  useEffect(() => {

    if (page !== "exam" || result) return;

    const timer = window.setInterval(

      () =>

        setRemaining((v) => {

          if (v <= 1) {

            window.clearInterval(timer);

            return 0;

          }

          return v - 1;

        }),

      1000

    );

    return () => window.clearInterval(timer);

  }, [page, result]);

  useEffect(() => {

    if (page === "exam" && remaining === 0 && !result) finishTest();

  }, [remaining, page, result]);

  const clock = `${String(Math.floor(remaining / 60)).padStart(

    2,

    "0"

  )}:${String(remaining % 60).padStart(2, "0")}`;

  const go = (p: Page) => {

    setNotice("");

    setPage(p);

    navigate(routeByPage[p]);

    window.scrollTo({ top: 0, behavior: "smooth" });

  };

  async function uploadPdf() {

    if (!selectedPdf) {

      setNotice("Choose a PDF file before uploading.");

      return;

    }

    if (!selectedPdf.name.toLowerCase().endsWith(".pdf")) {

      setNotice("Please choose a PDF file.");

      return;

    }

    setUploadingPdf(true);

    setNotice("");

    try {

      const formData = new FormData();

      formData.append("file", selectedPdf);

      const token = localStorage.getItem("intellilearn_access_token");

      const response = await fetch(`${API}/documents/upload`, {

        method: "POST",

        headers: token ? { Authorization: `Bearer ${token}` } : {},

        body: formData,

      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {

        throw new Error(data.detail || data.message || `Upload failed (${response.status})`);

      }

      setNotice(

        data.message ||

        "PDF uploaded and text stored. Topics will appear after extraction succeeds."

      );

      setSelectedPdf(null);

      // Refresh the subjects/topics page using the backend's existing endpoint.

      try {

        const topicData = await api<{

          subjects?: { name: string; topics: string[] }[];

        }>("/topics");

        const loadedSubjects: Subject[] = (topicData.subjects || []).map((item) => ({

          name: item.name,

          topics: item.topics || [],

          color: subjectColor(formatSubjectName(item.name)),

        }));

        setSubjects(loadedSubjects);

      } catch {

        // The PDF and its text may already be stored even if topic extraction is unavailable.

      }

    } catch (error) {

      setNotice(error instanceof Error ? error.message : "Could not upload this PDF.");

    } finally {

      setUploadingPdf(false);

    }

  }

  async function startTest() {

    setBusy(true);

    setNotice("");

    setResult(false);

    setAnswers({});

    setIndex(0);

    try {

      const data = await api<{ questions?: Question[] } | Question[]>(

        "/questions/generate",

        {

          subject,

          topic,

          difficulty:

            difficulty === "Recommended" ? "medium" : difficulty.toLowerCase(),

          count: questionCountByDuration[duration],

        }

      );

      const generatedQuestions = Array.isArray(data)

        ? data

        : data.questions ?? [];

      if (generatedQuestions.length === 0) {

        throw new Error(

          "The AI did not generate any questions. Please try again."

        );

      }

      setQuestions(

        generatedQuestions.map((q, i) => ({

          ...q,

          id: q.id ?? i + 1,

          options: Array.isArray(q.options) ? q.options : [],

        }))

      );

      setRemaining(duration * 60);
      setTestStartedAt(Date.now());

      go("exam");

    } catch (error) {

      setNotice(

        error instanceof Error

          ? error.message

          : "Failed to generate the AI test. Please try again."

      );

    } finally {

      setBusy(false);

    }

  }

  async function finishTest() {
    if (result) return;
    setResult(true);
    setPage("results");

    if (questions.length === 0) return;

    const durationSeconds = testStartedAt
      ? Math.max(0, Math.round((Date.now() - testStartedAt) / 1000))
      : Math.max(0, duration * 60 - remaining);
    const practicedTopics = Array.from(new Set(
      questions.map((question) => question.topic || topic).filter(Boolean)
    ));

    try {
      await api<{ saved: boolean; attempt_id: string }>("/dashboard/attempts", {
        subject,
        topic: topic || null,
        duration_seconds: durationSeconds,
        total_questions: questions.length,
        correct_answers: score,
        topics_practiced: practicedTopics,
      });
      setNotice("Test history saved successfully.");
    } catch (error) {
      setNotice(
        `Test completed, but history could not be saved: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  const score = useMemo(

    () =>

      questions.reduce(

        (n, q) => n + (answers[q.id] === q.correct_answer ? 1 : 0),

        0

      ),

    [questions, answers]

  );

  async function loadConversations() {
    try {
      const data = await api<{ conversations: ChatConversation[] }>("/chat/conversations");
      setConversations(data.conversations || []);
    } catch (error) {
      setNotice(`Could not load chat history: ${String(error)}`);
    }
  }

  async function createNewChat() {
    setBusy(true);
    setNotice("");
    try {
      const conversation = await api<ChatConversation>("/chat/conversations", { title: "New chat" });
      setActiveConversationId(conversation.id);
      setChatMessages([]);
      setTutorInput("");
      setTutorAnswer("");
      setSources([]);
      await loadConversations();
    } catch (error) {
      setNotice(`Could not create a new chat: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function openChat(conversation: ChatConversation) {
    setBusy(true);
    setNotice("");
    try {
      const data = await api<{ messages: ChatMessage[] }>(`/chat/conversations/${conversation.id}/messages`);
      setActiveConversationId(conversation.id);
      setChatMessages(data.messages || []);
      setTutorInput("");
      const lastAssistant = [...(data.messages || [])].reverse().find((message) => message.role === "assistant");
      setTutorAnswer(lastAssistant?.content || "");
      setSources(lastAssistant?.sources || []);
    } catch (error) {
      setNotice(`Could not open this conversation: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function askTutor() {
    const question = tutorInput.trim();
    if (!question || busy) return;
    setBusy(true);
    setNotice("");
    try {
      let conversationId = activeConversationId;
      if (!conversationId) {
        const created = await api<ChatConversation>("/chat/conversations", { title: "New chat" });
        conversationId = created.id;
        setActiveConversationId(conversationId);
      }
      const data = await api<{ messages: ChatMessage[]; retrieval_message?: string }>(
        `/chat/conversations/${conversationId}/messages`,
        { question }
      );
      setChatMessages((previous) => [...previous, ...(data.messages || [])]);
      const answer = (data.messages || []).find((message) => message.role === "assistant");
      setTutorAnswer(answer?.content || "No answer returned.");
      setSources(answer?.sources || []);
      setTutorInput("");
      if (data.retrieval_message) setNotice(data.retrieval_message);
      await loadConversations();
    } catch (error) {
      setNotice(`Could not send your message: ${String(error)}. Check that the backend is running at ${API}.`);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (page === "tutor" && authToken) {
      void loadConversations();
    }
  }, [page, authToken]);

  const Back = ({ to = "test-menu" }: { to?: Page }) => (

    <button className="back" onClick={() => go(to)}>

      <ArrowLeft size={16} /> Back

    </button>

  );

  const Eyebrow = ({ children }: { children: string }) => (

    <div className="eyebrow">{children}</div>

  );

  const Footer = () => (

    <footer className="footer">

      <span>AdaptiveLearning · Personalized practice</span>

      <span>Questions and scores are processed by the backend</span>

    </footer>

  );

  if (!authToken) {

    return (

      <AuthScreen

        onAuthenticated={(token, user) => {

          if (!token) {

            console.error("Login succeeded but no access token was returned.");

            return;

          }

          try {

            localStorage.setItem("intellilearn_access_token", token);

            localStorage.setItem("intellilearn_user", JSON.stringify(user));

            setAuthUser(user);

            setAuthToken(token);

          } catch (error) {

            console.error("Could not save login session:", error);

          }

        }}

      />

    );

  }

  const navItems = [

    { label: "Dashboard", icon: <LayoutDashboard size={19} />, onClick: () => go("dashboard"), active: page === "dashboard" },

    { label: "Exams", icon: <FileCheck2 size={19} />, onClick: () => go("test-menu"), active: ["test-menu", "subjects", "topics", "configure", "exam", "results"].includes(page) },

    { label: "Chat", icon: <MessageSquare size={19} />, onClick: () => go("tutor"), active: page === "tutor" },

    { label: "Upload", icon: <Upload size={19} />, onClick: () => go("upload"), active: page === "upload" },

  ];

  return (

    <>

      <AppShell
        userName={authUser?.full_name || "Student workspace"}
        navItems={navItems}
        onLogout={() => {
          localStorage.removeItem("intellilearn_access_token");
          localStorage.removeItem("intellilearn_user");
          setAuthToken("");
          setAuthUser(null);
          navigate("/");
        }}
      >
        <main className="container app-page-content">

          {page === "dashboard" && (

            <>

              <section className="welcome">

                <div>

                  <Eyebrow>YOUR LEARNING SPACE</Eyebrow>

                  <h1>Welcome back!</h1>

                  <p>

                    Continue learning, practice your subjects, and track your

                    progress.

                  </p>

                </div>

                <button className="white-button" onClick={() => go("test-menu")}>

                  Take a test <ArrowRight size={17} />

                </button>

              </section>

              <section className="stats">

                <Stat icon={<Target />} label="Average accuracy" value={dashboardSummary ? `${dashboardSummary.average_accuracy}%` : dashboardLoading ? "Loading…" : "0%"} />

                <Stat icon={<NotebookPen />} label="Tests completed" value={dashboardSummary ? String(dashboardSummary.tests_completed) : dashboardLoading ? "Loading…" : "0"} />

                <Stat icon={<BookOpen />} label="Topics practiced" value={dashboardSummary ? String(dashboardSummary.topics_practiced) : dashboardLoading ? "Loading…" : "0"} />

                <Stat icon={<Timer />} label="Study time" value={dashboardSummary ? `${Math.floor(dashboardSummary.study_time_minutes / 60)}h ${dashboardSummary.study_time_minutes % 60}m` : dashboardLoading ? "Loading…" : "0m"} />

              </section>

              <section className="panel history">

                <div className="panel-heading">

                  <div>

                    <h3>Recent AI test history</h3>

                    <p>Your latest completed tests</p>

                  </div>

                  <button className="text-button" onClick={() => go("results")}>

                    View all <ArrowRight size={15} />

                  </button>

                </div>

                {testHistory.length === 0 ? (
                  <div className="empty-state">
                    <NotebookPen size={38} />
                    <strong>{dashboardLoading ? "Loading test history…" : "No completed tests yet"}</strong>
                    <span>Your recent tests will appear here after you complete one.</span>
                  </div>
                ) : (
                  <div style={{ display: "grid", gap: 0 }}>
                    {testHistory.slice(0, 5).map((test) => (
                      <div key={test.session_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, padding: "18px 24px", borderTop: "1px solid #edf0f6", flexWrap: "wrap" }}>
                        <div>
                          <strong>{test.subject}</strong>
                          <div style={{ color: "#78849a", fontSize: 13, marginTop: 4 }}>{test.topic || "All topics"} · {new Date(test.completed_at).toLocaleString()}</div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <strong>{test.score}/{test.total_questions}</strong>
                          <div style={{ color: "#5140df", fontSize: 13, marginTop: 4 }}>{test.accuracy_percent}% accuracy</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

              </section>

            </>

          )}

          {page === "test-menu" && (

            <>

              <div className="choice-grid">

                <Choice

                  icon={<Brain />}

                  title="AI Full Mock Test"

                  desc="Generate a practice test across subjects using your selected duration and difficulty."

                  button="Configure AI mock"

                  onClick={() => {

                    setSubject("All subjects");

                    setTopic("All topics");

                    go("configure");

                  }}

                />

                <Choice

                  green

                  icon={<BookOpen />}

                  title="AI Subject Test"

                  desc="Choose a subject and topic to generate focused practice questions."

                  button="Choose a subject"

                  onClick={() => go("subjects")}

                />

              </div>

            </>

          )}

          {page === "exam" && current && (

            <>

              <Back to="test-menu" />

              <Eyebrow>ADAPTIVE LEARNING</Eyebrow>

              <h1 className="page-title">

                {subject === "All subjects" ? "Full Mock Test" : "Subject Test"}

              </h1>

              <div className="exam-layout">

                <section className="panel question-panel">

                  <div className="question-meta">

                    <div>

                      <span className="purple-text">

                        {subject === "All subjects" ? "Full Mock Test" : subject}

                      </span>

                      <p>

                        Question {index + 1} of {questions.length}

                      </p>

                    </div>

                    <span className="timer">

                      <Clock3 size={18} />

                      {clock}

                    </span>

                  </div>

                  <div className="chips">

                    <span>{current.difficulty || "Easy"}</span>

                    <span>{current.subject || subject}</span>

                    <span>{current.topic || topic}</span>

                  </div>

                  <h2>{current.question}</h2>

                  <div className="options">

                    {(current.options || []).map((opt, i) => (

                      <button

                        key={i}

                        className={`option ${answers[current.id] === opt ? "chosen" : ""

                          }`}

                        onClick={() =>

                          setAnswers((a) => ({ ...a, [current.id]: opt }))

                        }

                      >

                        <span>{String.fromCharCode(65 + i)}</span>

                        {opt}

                      </button>

                    ))}

                  </div>

                  <div className="question-actions">

                    <button

                      className="outline-button"

                      disabled={index === 0}

                      onClick={() => setIndex((i) => i - 1)}

                    >

                      Previous

                    </button>

                    {index < questions.length - 1 ? (

                      <button

                        className="primary-button"

                        onClick={() => setIndex((i) => i + 1)}

                      >

                        Next question <ArrowRight size={16} />

                      </button>

                    ) : (

                      <button className="primary-button" onClick={finishTest}>

                        Submit test

                      </button>

                    )}

                  </div>

                </section>

                <aside className="panel navigator">

                  <h3>Question navigator</h3>

                  <p>

                    {answered} of {questions.length} answered

                  </p>

                  <div className="number-grid">

                    {questions.map((q, i) => (

                      <button

                        key={q.id}

                        className={`${index === i ? "active" : ""} ${answers[q.id] ? "answered" : ""

                          }`}

                        onClick={() => setIndex(i)}

                      >

                        {i + 1}

                      </button>

                    ))}

                  </div>

                  <div className="legend">

                    <span>● Green: answered</span>

                    <span>● Grey: unanswered</span>

                    <span>● Indigo: current question</span>

                  </div>

                  <button className="submit-button" onClick={finishTest}>

                    Submit test

                  </button>

                </aside>

              </div>

            </>

          )}

          {page === "subjects" && (

            <>

              <Back />

              <Eyebrow>ADAPTIVE LEARNING</Eyebrow>

              <h1 className="page-title">Subject Tests</h1>

              <p className="page-intro">

                Choose a subject to see its available topics and tests.

              </p>

              <div className="subject-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 250px), 1fr))", gap: 20, width: "100%", minWidth: 0 }}>

                {subjects.map((s) => (

                  <button

                    className="subject-card"

                    style={{ width: "100%", minWidth: 0, boxSizing: "border-box", textAlign: "left", overflowWrap: "anywhere" }}

                    key={s.name}

                    onClick={() => {

                      setSubject(s.name);

                      setTopic(s.topics[0] || "");

                      go("topics");

                    }}

                  >

                    <span className={`subject-icon ${s.color}`}>

                      {s.name === "Chemistry" ? (

                        <FlaskConical />

                      ) : s.name === "Mathematics" ? (

                        <Target />

                      ) : (

                        <Atom />

                      )}

                    </span>

                    <h3 style={{ overflowWrap: "anywhere" }}>{formatSubjectName(s.name)}</h3>

                    <p>{s.topics.length} topics available</p>

                    <span className="text-button">

                      View topics <ArrowRight size={15} />

                    </span>

                  </button>

                ))}

              </div>

            </>

          )}

          {page === "topics" && (

            <>

              <Back to="subjects" />

              <Eyebrow>AI-GENERATED EXAMS</Eyebrow>

              <h1 className="page-title">Choose a topic</h1>

              <div className="subject-banner">

                <BookOpen />

                <div>

                  <b>{subject}</b>

                  <p>

                    Select a topic and generate a new AI-powered practice test.

                  </p>

                </div>

              </div>

              <div className="topic-grid">

                {(subjects.find((s) => s.name === subject)?.topics || []).map(

                  (t) => (

                    <article className="topic-card" key={t}>

                      <div className="topic-top">

                        <div>

                          <h3 style={{ color: "#17365d", overflowWrap: "anywhere" }}>{t}</h3>

                          <p>{topicDescription(t)}</p>

                        </div>

                        <button

                          className="help-icon"

                          title={`About ${t}`}

                          onClick={() =>

                            setNotice(

                              `${t}: practise the main concepts and problem-solving skills for this topic.`

                            )

                          }

                        >

                          <CircleHelp size={20} />

                        </button>

                      </div>

                      <p className="saved-count">

                        Generate fresh questions with AI

                      </p>

                      <div className="topic-actions">

                        <button

                          className="primary-button"

                          onClick={() => {

                            setTopic(t);

                            go("configure");

                          }}

                        >

                          AI-generated test

                        </button>

                      </div>

                    </article>

                  )

                )}

              </div>

            </>

          )}

          {page === "configure" && (

            <>

              <Back to={subject === "All subjects" ? "test-menu" : "topics"} />

              <Eyebrow>ADAPTIVE LEARNING</Eyebrow>

              <h1 className="page-title">Configure your test</h1>

              <section className="panel configure-card">

                <div className="configure-heading">

                  <span className="brain-tile">

                    <Brain />

                  </span>

                  <div>

                    <h3>

                      {subject === "All subjects"

                        ? "AI-generated full mock test"

                        : "AI-generated topic test"}

                    </h3>

                    <p>

                      {subject} · {topic}

                    </p>

                  </div>

                </div>

                <h3>1. Choose duration</h3>

                <div className="duration-row">

                  {[10, 15, 30, 60, 90, 180].map((n) => (

                    <button

                      key={n}

                      className={duration === n ? "selected" : ""}

                      onClick={() => setDuration(n)}

                    >

                      {n} min

                    </button>

                  ))}

                </div>

                <p className="helper">

                  {questionCountByDuration[duration]} questions · {duration}{" "}

                  minutes to complete the test.

                </p>

                <h3 className="difficulty-title">2. Choose difficulty</h3>

                <div className="difficulty-grid">

                  {[

                    ["Easy", "Build confidence with fundamentals"],

                    ["Medium", "Balanced conceptual practice"],

                    ["Hard", "Challenge yourself with advanced questions"],

                    ["Recommended", "Adapts to previous performance"],

                  ].map(([d, desc]) => (

                    <button

                      key={d}

                      className={`difficulty-card ${difficulty === d ? "selected" : ""

                        }`}

                      onClick={() => setDifficulty(d)}

                    >

                      <b>{d}</b>

                      <span>{desc}</span>

                    </button>

                  ))}

                </div>

                <button

                  className="primary-button full-button"

                  disabled={busy}

                  onClick={startTest}

                >

                  <Brain size={18} />

                  {busy ? "Generating…" : "Generate AI test"}

                </button>

              </section>

            </>

          )}

          {page === "results" && (

            <>

              <Eyebrow>TEST COMPLETED</Eyebrow>

              <h1 className="page-title">Your test results</h1>

              <section className="result-hero">

                <div>

                  <span>TEST COMPLETED</span>

                  <h2>{topic} Assessment</h2>

                  <p>Review your answers and explanations below.</p>

                </div>

                <div className="score-box">

                  <span>Your score</span>

                  <strong>

                    {Math.round((score / Math.max(questions.length, 1)) * 100)}%

                  </strong>

                  <small>

                    {score}/{questions.length} correct

                  </small>

                </div>

              </section>

              <div className="result-stats">

                <MiniStat label="Correct" value={String(score)} />

                <MiniStat label="Incorrect" value={String(answered - score)} />

                <MiniStat

                  label="Unanswered"

                  value={String(questions.length - answered)}

                />

                <MiniStat

                  label="Total questions"

                  value={String(questions.length)}

                />

              </div>

              <section className="panel review-panel">

                <h3>Review answers and explanations</h3>

                {questions.map((q, i) => (

                  <article className="review-card" key={q.id}>

                    <small>

                      QUESTION {i + 1} · {q.topic || topic}

                    </small>

                    <h4>{q.question}</h4>

                    <p className="correct-answer">

                      ✓ {q.correct_answer || "Answer not supplied"} · Correct

                      answer

                    </p>

                    {answers[q.id] && (

                      <p

                        className={

                          answers[q.id] === q.correct_answer

                            ? "correct-answer"

                            : "wrong-answer"

                        }

                      >

                        {answers[q.id] === q.correct_answer ? "✓" : "×"} Your

                        answer: {answers[q.id]}

                      </p>

                    )}

                    <div className="explanation">

                      <b>EXPLANATION</b>

                      <p>

                        {q.explanation ||

                          "No explanation was supplied for this question."}

                      </p>

                    </div>

                  </article>

                ))}

              </section>

              <div className="result-actions">

                <button

                  className="outline-button"

                  onClick={() => go("test-menu")}

                >

                  Back to test menu

                </button>

                <button

                  className="primary-button"

                  onClick={() => {

                    go("configure");

                  }}

                >

                  Retake test

                </button>

              </div>

            </>

          )}

          {page === "upload" && (

            <>

              <Back to="dashboard" />

              <Eyebrow>ADAPTIVE LEARNING</Eyebrow>

              <h1 className="page-title">Upload study material</h1>

              <p className="page-intro">

                Upload a text-based PDF. Its filename will identify the subject, and extracted topics will appear under that subject.

              </p>

              <section

                className="panel"

                style={{

                  maxWidth: 900,

                  padding: 28,

                  border: "1px solid #dfe5f0",

                  borderRadius: 18,

                  background: "#ffffff",

                }}

              >

                <div

                  style={{

                    border: "2px dashed #cbd5e8",

                    borderRadius: 14,

                    padding: "32px 20px",

                    textAlign: "center",

                    background: "#f8faff",

                  }}

                >

                  <Upload size={34} color="#5140df" style={{ marginBottom: 12 }} />

                  <h2 style={{ margin: "0 0 8px", color: "#172b4d", fontSize: 20 }}>

                    Choose your PDF

                  </h2>

                  <p style={{ margin: "0 0 20px", color: "#71809a" }}>

                    Select a study PDF from your computer (PDF only).

                  </p>

                  <input

                    type="file"

                    accept="application/pdf,.pdf"

                    onChange={(event) => {

                      setSelectedPdf(event.target.files?.[0] || null);

                      setNotice("");

                    }}

                    style={{

                      display: "block",

                      maxWidth: "100%",

                      margin: "0 auto",

                      color: "#263b5e",

                    }}

                  />

                  {selectedPdf && (

                    <p style={{ margin: "16px 0 0", color: "#172b4d", fontWeight: 700, overflowWrap: "anywhere" }}>

                      Selected: {selectedPdf.name}

                    </p>

                  )}

                </div>

                <button

                  className="primary-button"

                  type="button"

                  disabled={!selectedPdf || uploadingPdf}

                  onClick={uploadPdf}

                  style={{ marginTop: 18, opacity: !selectedPdf || uploadingPdf ? 0.65 : 1 }}

                >

                  {uploadingPdf ? "Uploading PDF..." : "Upload PDF"}

                </button>

                {notice && (

                  <div

                    role="status"

                    style={{

                      marginTop: 18,

                      padding: "12px 14px",

                      borderRadius: 10,

                      background: "#fff7df",

                      border: "1px solid #f4df9c",

                      color: "#664b00",

                      overflowWrap: "anywhere",

                    }}

                  >

                    {notice}

                  </div>

                )}

                <p style={{ margin: "18px 0 0", color: "#71809a", fontSize: 13, lineHeight: 1.6 }}>

                  After upload, open Exams to view the subject and any topics successfully extracted from the PDF.

                </p>

              </section>

            </>

          )}

          {page === "tutor" && (

            <div className="tutor-shell">

              <aside className="chat-sidebar">

                <h3>Your conversations</h3>

                <button

                  className="primary-button"

                  onClick={() => { void createNewChat(); }}

                >

                  <MessageSquare size={16} /> New chat

                </button>

                <small>RECENT CHATS</small>

                {conversations.length === 0 ? (
                  <p>Your conversations will appear here.</p>
                ) : (
                  <div className="recent-chat-list" style={{ display: "grid", gap: 6, marginTop: 12 }}>
                    {conversations.map((conversation) => (
                      <button
                        key={conversation.id}
                        type="button"
                        className={`recent-chat-item ${activeConversationId === conversation.id ? "active" : ""}`}
                        style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left", padding: "10px", borderRadius: 8, border: activeConversationId === conversation.id ? "1px solid #8b5cf6" : "1px solid transparent", background: activeConversationId === conversation.id ? "rgba(139,92,246,0.12)" : "transparent", cursor: "pointer" }}
                        onClick={() => { void openChat(conversation); }}
                        disabled={busy}
                      >
                        <MessageSquare size={15} />
                        <span>{conversation.title}</span>
                      </button>
                    ))}
                  </div>
                )}

                <button

                  className="back-dashboard"

                  onClick={() => go("dashboard")}

                >

                  <ArrowLeft size={16} /> Back to Dashboard

                </button>

              </aside>

              <section className="tutor-main">

                <div className="tutor-head">

                  <span className="brain-tile">

                    <Brain />

                  </span>

                  <div>

                    <b>AI Tutor</b>

                    <p>Your personal learning assistant</p>

                  </div>

                  <span className="study-pill">Study mode</span>

                </div>

                {chatMessages.length === 0 ? (
                  <div className="tutor-empty">
                    <span className="brain-tile big"><Brain size={28} /></span>
                    <h2>What would you like to learn?</h2>
                    <p>Ask a question, explore a concept, or learn from your study materials.</p>
                    <div className="prompt-grid">
                      {[
                        "Explain a concept in simple words",
                        "Help me understand a question",
                        "Give me a step-by-step solution",
                        "Ask questions about my PDF",
                      ].map((suggestion, index) => (
                        <button key={suggestion} onClick={() => setTutorInput([
                          "Explain a concept in simple words: ",
                          "Help me understand this question: ",
                          "Give me a step-by-step solution for: ",
                          "Ask a question about my uploaded PDF: ",
                        ][index])}>
                          {[<Brain />, <MessageSquare />, <Lightbulb />, <NotebookPen />][index]}
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="tutor-response chat-transcript" style={{ display: "grid", gap: 18, paddingBottom: 18 }}>
                    {chatMessages.map((message) => (
                      <article key={message.id} className={`chat-message ${message.role}`}
                        style={{ padding: 16, borderRadius: 12, background: message.role === "user" ? "rgba(139,92,246,0.10)" : "rgba(127,127,127,0.06)", overflowWrap: "anywhere" }}>
                        <b>{message.role === "user" ? "You" : "AI Tutor"}</b>
                        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                          {message.content}
                        </ReactMarkdown>
                      </article>
                    ))}
                  </div>
                )}

                {notice && <p className="notice">{notice}</p>}

                <div className="tutor-compose">

                  <textarea

                    value={tutorInput}

                    onChange={(e) => setTutorInput(e.target.value)}

                    placeholder="Ask your tutor a question…"

                    onKeyDown={(e) => {

                      if (e.key === "Enter" && !e.shiftKey) {

                        e.preventDefault();

                        askTutor();

                      }

                    }}

                  />

                  <div className="compose-bottom">

                    <button

                      className="send-button"

                      disabled={busy || !tutorInput.trim()}

                      onClick={askTutor}

                    >

                      <Send size={18} />

                    </button>

                  </div>

                  <small>Enter to send · Shift + Enter for a new line</small>

                </div>

              </section>

            </div>

          )}

          {notice && page !== "tutor" && (

            <div className="notice">

              <span>{notice}</span>

              <button onClick={() => setNotice("")}>

                <X size={16} />

              </button>

            </div>

          )}

        </main>
      </AppShell>

      <Footer />

    </>

  );

}

function Stat({

  icon,

  label,

  value,

}: {

  icon: React.ReactNode;

  label: string;

  value: string;

}) {

  return (

    <div className="stat-card">

      <span>{label}</span>

      <i>{icon}</i>

      <strong>{value}</strong>

    </div>

  );

}

function Quick({

  icon,

  title,

  desc,

  onClick,

}: {

  icon: React.ReactNode;

  title: string;

  desc: string;

  onClick: () => void;

}) {

  return (

    <button className="quick-card" onClick={onClick}>

      <span>{icon}</span>

      <div>

        <b>{title}</b>

        <p>{desc}</p>

      </div>

      <ArrowRight size={16} />

    </button>

  );

}

function Choice({

  icon,

  title,

  desc,

  button,

  onClick,

  green = false,

}: {

  icon: React.ReactNode;

  title: string;

  desc: string;

  button: string;

  onClick: () => void;

  green?: boolean;

}) {

  return (

    <article className={`choice-card ${green ? "green-card" : ""}`}>

      <span className="choice-icon">{icon}</span>

      <ChevronRight className="choice-arrow" />

      <h2>{title}</h2>

      <p>{desc}</p>

      <button

        className={`primary-button ${green ? "green-button" : ""}`}

        onClick={onClick}

      >

        {button}

      </button>

    </article>

  );

}

function MiniStat({ label, value }: { label: string; value: string }) {

  return (

    <div className="mini-stat">

      <span>{label}</span>

      <b>{value}</b>

    </div>

  );

}

function formatSubjectName(name: string) {

  const normalized = name

    .replace(/\.pdf$/i, "")

    .replace(/\s*\\(\d+\\)$/, "")

    .replace(/^intellilearn_ai_/, "")

    .replace(/^intellilearn_/, "")

    .replace(/_study_material$/i, "")

    .replace(/_jee_100_questions$/i, "")

    .replace(/_/g, " ")

    .trim()

    .toLowerCase();

  const knownNames: Record<string, string> = {

    physics: "Physics",

    biology: "Biology",

    chemistry: "Chemistry",

    "computer science": "Computer Science",

    mathematics: "Mathematics",

  };

  return knownNames[normalized] || normalized.replace(/\b\w/g, (char) => char.toUpperCase());

}

function topicDescription(t: string) {

  const d: Record<string, string> = {

    "Coordinate Geometry": "Points, lines and geometric equations",

    Functions: "Functions, domains and ranges",

    "Limits and Derivatives": "Limits and differential calculus",

    "Matrices and Determinants": "Matrix operations and determinants",

    Probability: "Probability and basic events",

    "Quadratic Equations": "Quadratic equations and their roots",

    "Atomic Structure": "Atoms, particles and electronic configuration",

    "Laws of Motion": "Force, inertia and Newton’s laws",

  };

  return d[t] || `Core concepts and practice in ${t.toLowerCase()}`;

}

function AuthScreen({

  onAuthenticated,

}: {

  onAuthenticated: (

    token: string,

    user: { full_name: string; email: string }

  ) => void;

}) {

  const [mode, setMode] = useState<"login" | "signup">("login");

  const [fullName, setFullName] = useState("");

  const [email, setEmail] = useState("");

  const [password, setPassword] = useState("");

  const [error, setError] = useState("");

  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {

    event.preventDefault();

    setError("");

    setBusy(true);

    try {

      const payload =

        mode === "signup"

          ? { full_name: fullName.trim(), email: email.trim(), password }

          : { email: email.trim(), password };

      const response = await api<{

        access_token: string;

        user: { full_name: string; email: string };

      }>(`/auth/${mode}`, payload);

      onAuthenticated(response.access_token, response.user);

    } catch (e) {

      setError(

        e instanceof Error

          ? e.message

          : "Authentication failed. Please try again."

      );

    } finally {

      setBusy(false);

    }

  }

  const field: React.CSSProperties = {

    width: "100%",

    boxSizing: "border-box",

    padding: "13px 14px",

    border: "1px solid #d8deea",

    borderRadius: 10,

    fontSize: 15,

    outlineColor: "#6257d9",

  };

  return (

    <div

      style={{

        minHeight: "100vh",

        display: "grid",

        placeItems: "center",

        padding: 24,

        background: "linear-gradient(135deg,#f5f7ff,#eef7ff)",

        fontFamily: "Inter, system-ui, sans-serif",

        color: "#17213b",

      }}

    >

      <section

        style={{

          width: "100%",

          maxWidth: 440,

          background: "white",

          border: "1px solid #e5e9f3",

          borderRadius: 22,

          padding: 32,

          boxShadow: "0 18px 60px rgba(30,45,90,.10)",

        }}

      >

        <div

          style={{

            display: "flex",

            alignItems: "center",

            gap: 12,

            marginBottom: 26,

          }}

        >

          <span

            style={{

              display: "grid",

              placeItems: "center",

              width: 48,

              height: 48,

              borderRadius: 14,

              color: "white",

              background: "#6257d9",

            }}

          >

            <Brain size={26} />

          </span>

          <div>

            <div style={{ fontWeight: 800, fontSize: 22 }}>IntelliLearn AI</div>

            <div style={{ color: "#68738a", fontSize: 13 }}>

              Your personal learning space

            </div>

          </div>

        </div>

        <h1 style={{ fontSize: 27, margin: "0 0 8px" }}>

          {mode === "login" ? "Welcome back" : "Create your account"}

        </h1>

        <p style={{ color: "#68738a", margin: "0 0 24px", lineHeight: 1.5 }}>

          {mode === "login"

            ? "Log in to continue learning and practicing."

            : "Sign up to start your personalized learning journey."}

        </p>

        <form onSubmit={submit} style={{ display: "grid", gap: 14 }}>

          {mode === "signup" && (

            <label

              style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}

            >

              Full name

              <input

                style={field}

                autoComplete="name"

                value={fullName}

                onChange={(e) => setFullName(e.target.value)}

                required

                minLength={2}

                maxLength={100}

                placeholder="Your full name"

              />

            </label>

          )}

          <label

            style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}

          >

            Email address

            <input

              style={field}

              type="email"

              autoComplete="email"

              value={email}

              onChange={(e) => setEmail(e.target.value)}

              required

              placeholder="you@example.com"

            />

          </label>

          <label

            style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}

          >

            Password

            <input

              style={field}

              type="password"

              autoComplete={

                mode === "login" ? "current-password" : "new-password"

              }

              value={password}

              onChange={(e) => setPassword(e.target.value)}

              required

              minLength={mode === "signup" ? 8 : 1}

              maxLength={128}

              placeholder={

                mode === "signup"

                  ? "At least 8 characters"

                  : "Enter your password"

              }

            />

          </label>

          {error && (

            <div

              role="alert"

              style={{

                color: "#b42318",

                background: "#fff2f0",

                padding: 12,

                borderRadius: 9,

                fontSize: 13,

              }}

            >

              {error}

            </div>

          )}

          <button

            type="submit"

            disabled={busy}

            className="primary-button"

            style={{

              width: "100%",

              justifyContent: "center",

              marginTop: 5,

              opacity: busy ? 0.7 : 1,

            }}

          >

            {busy

              ? "Please wait…"

              : mode === "login"

                ? "Log in"

                : "Create account"}

          </button>

        </form>

        <p

          style={{

            textAlign: "center",

            color: "#68738a",

            fontSize: 14,

            margin: "22px 0 0",

          }}

        >

          {mode === "login"

            ? "New to IntelliLearn AI?"

            : "Already have an account?"}{" "}

          <button

            type="button"

            onClick={() => {

              setMode(mode === "login" ? "signup" : "login");

              setError("");

            }}

            style={{

              border: 0,

              background: "transparent",

              color: "#6257d9",

              fontWeight: 750,

              cursor: "pointer",

            }}

          >

            {mode === "login" ? "Sign up" : "Log in"}

          </button>

        </p>

      </section>

    </div>

  );

}

export default App;
