"use client";

import { ToastContainer as ReactToastContainer } from "react-toastify";

export function ToastContainer() {
 return (
 <ReactToastContainer
 position="bottom-left"
 autoClose={4000}
 hideProgressBar={false}
 newestOnTop
 closeOnClick
 closeButton={false}
 rtl
 pauseOnFocusLoss={false}
 draggable
 pauseOnHover
 theme="light"
 toastClassName="text-sm !min-h-0 !py-3 !px-4"
 />
 );
}
