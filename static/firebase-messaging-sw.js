importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-messaging-compat.js');
// Config placeholder — replace with your Firebase project
firebase.initializeApp({
  apiKey: "AIzaSyDemo",
  authDomain: "drcar-demo.firebaseapp.com",
  projectId: "drcar-demo",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abcdef"
});
const messaging = firebase.messaging();
messaging.onBackgroundMessage(payload => {
  self.registration.showNotification(payload.notification?.title || 'Dr. Car', {
    body: payload.notification?.body || 'لديك إشعار جديد',
    icon: '/static/images/logo.svg'
  });
});