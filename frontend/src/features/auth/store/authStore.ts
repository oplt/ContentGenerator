type AuthState = {
    accessToken: string | null;
    setAccessToken: (token: string | null) => void;
};

class AuthStoreImpl implements AuthState {
    accessToken: string | null = null;

    setAccessToken = (token: string | null) => {
        this.accessToken = token;
    };
}

export const authStore = new AuthStoreImpl();
