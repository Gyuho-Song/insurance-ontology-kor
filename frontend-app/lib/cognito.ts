import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
} from 'amazon-cognito-identity-js';

const POOL_ID = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID || 'us-west-2_XXXXXXXXX';
const CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID || 'xxxxxxxxxxxxxxxxxxxxxxxxxx';

const userPool = new CognitoUserPool({
  UserPoolId: POOL_ID,
  ClientId: CLIENT_ID,
});

export interface AuthResult {
  idToken: string;
  accessToken: string;
  email: string;
}

export class NewPasswordRequiredError extends Error {
  constructor() {
    super('NEW_PASSWORD_REQUIRED');
    this.name = 'NewPasswordRequiredError';
  }
}

// Module-level ref to the CognitoUser that needs a password change
let pendingUser: CognitoUser | null = null;
let pendingUserAttributes: Record<string, string> = {};

function setSessionCookie(session: CognitoUserSession): AuthResult {
  const idToken = session.getIdToken().getJwtToken();
  const accessToken = session.getAccessToken().getJwtToken();
  const email = session.getIdToken().decodePayload().email as string;
  document.cookie = `cognito-id-token=${idToken}; path=/; max-age=3600; SameSite=Lax`;
  return { idToken, accessToken, email };
}

export function signIn(email: string, password: string): Promise<AuthResult> {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: userPool });
    const authDetails = new AuthenticationDetails({ Username: email, Password: password });

    user.authenticateUser(authDetails, {
      onSuccess: (session) => resolve(setSessionCookie(session)),
      onFailure: (err) => reject(err),
      newPasswordRequired: (userAttributes) => {
        // Store the user so completeNewPassword can use it
        pendingUser = user;
        pendingUserAttributes = { ...userAttributes };
        delete pendingUserAttributes.email_verified;
        delete pendingUserAttributes.email;
        reject(new NewPasswordRequiredError());
      },
    });
  });
}

export function completeNewPassword(newPassword: string): Promise<AuthResult> {
  return new Promise((resolve, reject) => {
    if (!pendingUser) {
      reject(new Error('No pending password change. Please sign in first.'));
      return;
    }
    pendingUser.completeNewPasswordChallenge(newPassword, pendingUserAttributes, {
      onSuccess: (session) => {
        pendingUser = null;
        pendingUserAttributes = {};
        resolve(setSessionCookie(session));
      },
      onFailure: (err) => reject(err),
    });
  });
}

export function getSession(): Promise<AuthResult | null> {
  return new Promise((resolve) => {
    const user = userPool.getCurrentUser();
    if (!user) {
      resolve(null);
      return;
    }
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session?.isValid()) {
        resolve(null);
        return;
      }
      resolve(setSessionCookie(session));
    });
  });
}

export function signOut(): void {
  const user = userPool.getCurrentUser();
  if (user) {
    user.signOut();
  }
  document.cookie = 'cognito-id-token=; path=/; max-age=0';
}
