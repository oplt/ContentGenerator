class AuthStore {
  accessToken: string | null = null;

  setAccessToken(token: string | null) {
    this.accessToken = token;
  }
}

export const authStore = new AuthStore();
