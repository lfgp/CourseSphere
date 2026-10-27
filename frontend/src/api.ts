import type { Dispatch, SetStateAction } from 'react';
import { auth } from './firebase';
import { createUserWithEmailAndPassword, onAuthStateChanged, signInWithEmailAndPassword } from 'firebase/auth';
import { toast } from 'react-toastify';

// Relative URLs keep credentials on the application's origin. Vite proxies /api locally.
async function apiRequest(path: string, options: RequestInit = {}) {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Invalid API path');
  const user = auth.currentUser;
  if (!user) throw new Error('Please log in to continue.');
  const idToken = await user.getIdToken();
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
      Authorization: `Bearer ${idToken}`,
    },
    cache: 'no-store',
    credentials: 'omit',
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function inputValue(id: string): string {
  return (document.getElementById(id) as HTMLInputElement | HTMLTextAreaElement | null)?.value || '';
}

async function createUser(email: string, password: string) {
  return createUserWithEmailAndPassword(auth, email, password);
}

async function performSignup() {
  try {
    await createUser(inputValue('signup-email-input'), inputValue('signup-password-input'));
    window.location.replace('/');
  } catch {
    toast.error('Unable to create your account. Check your details and try again.');
  }
}

async function performLogin() {
  try {
    await signInWithEmailAndPassword(auth, inputValue('login-email-input'), inputValue('login-password-input'));
    window.location.replace('/');
  } catch {
    toast.error('Unable to log in. Check your details and try again.');
  }
}

async function setProfileInfoIfLoggedIn(
  setMajors: Dispatch<SetStateAction<string[]>>,
  setMinors: Dispatch<SetStateAction<string[]>>,
  setYear: Dispatch<SetStateAction<string>>,
  setCollege: Dispatch<SetStateAction<string>>,
  setCourses: Dispatch<SetStateAction<string[]>>,
  setAbout: Dispatch<SetStateAction<string>>,
) {
  return onAuthStateChanged(auth, async (user) => {
    if (!user) return;
    try {
      const data = await apiRequest('/users/info');
      setMajors(data.majors || []);
      setMinors(data.minors || []);
      setCourses(data.courses || []);
      setYear(data.year || '');
      setCollege(data.college || '');
      setAbout(data.about || '');
      const aboutInput = document.getElementById('info-output') as HTMLTextAreaElement | null;
      if (aboutInput) aboutInput.value = data.about || '';
    } catch {
      toast.error('Failed to load your profile.');
    }
  });
}

async function saveProfileChanges(majors: string[], minors: string[], courses: string[]) {
  try {
    await apiRequest('/users/info', {
      method: 'POST',
      body: JSON.stringify({ majors, minors, courses,
        year: inputValue('year-output'), college: inputValue('college-output'), about: inputValue('info-output') }),
    });
    toast.success('Successfully saved your information!');
  } catch {
    toast.error('Failed to save your information.');
  }
}

async function fetchCourseSphereResponse(query: string) {
  return apiRequest('/users/query', { method: 'POST', body: JSON.stringify({ query }) });
}

async function saveCourseSphereChat(chatId: string, messages: Message[]) {
  return apiRequest(`/chats/${encodeURIComponent(chatId)}/messages`, {
    method: 'POST', body: JSON.stringify({ messages }),
  });
}

async function updateCourseSphereChat(chatId: string, messageId: string, updatedContent: string) {
  return apiRequest(`/chats/${encodeURIComponent(chatId)}/messages/${encodeURIComponent(messageId)}`, {
    method: 'PUT', body: JSON.stringify({ content: updatedContent }),
  });
}

async function deleteCourseSphereChat(chatId: string, messageId: string) {
  return apiRequest(`/chats/${encodeURIComponent(chatId)}/messages/${encodeURIComponent(messageId)}`, { method: 'DELETE' });
}

async function h(data: unknown): Promise<string> {
  const result = await apiRequest('/hash', { method: 'POST', body: JSON.stringify(data) });
  return result.messageID;
}

export {
  apiRequest, createUser, performSignup, performLogin, saveProfileChanges,
  setProfileInfoIfLoggedIn, fetchCourseSphereResponse, saveCourseSphereChat,
  updateCourseSphereChat, deleteCourseSphereChat, h,
};
