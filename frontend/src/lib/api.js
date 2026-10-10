import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

export const errMsg = (e) =>
  typeof e?.response?.data?.detail === "string"
    ? e.response.data.detail
    : "Something went wrong. Try again.";
