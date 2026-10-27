export const useFirebaseEmulators = import.meta.env.VITE_USE_FIREBASE_EMULATORS === "true";

export default useFirebaseEmulators ? {
  apiKey: "demo-coursesphere-key",
  authDomain: "localhost",
  projectId: "demo-coursesphere",
  databaseURL: "https://demo-coursesphere-default-rtdb.firebaseio.com",
  appId: "demo-coursesphere",
} : {
  apiKey: "AIzaSyD_i3HIL4SYkf2AEmKWs2dunhq7m1Glbc4",
  authDomain: "coursesphere-8bd9a.firebaseapp.com",
  databaseURL: "https://coursesphere-8bd9a-default-rtdb.firebaseio.com",
  projectId: "coursesphere-8bd9a",
  storageBucket: "coursesphere-8bd9a.appspot.com",
  messagingSenderId: "728789297654",
  appId: "1:728789297654:web:6b699e8b5ebebc8a8d3fd7",
  measurementId: "G-PM7PMGBE0R"
};
