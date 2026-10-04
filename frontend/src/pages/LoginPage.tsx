import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate, Link } from 'react-router-dom';
import { loginSchema, type LoginInput } from '../schemas';
import { useAuth } from '../hooks/useAuth';
import toast from 'react-hot-toast';
import { extractErrorMessage } from '../services/errors';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [serverError, setServerError] = useState('');

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginInput) => {
    try {
      setServerError('');
      await login(data.email, data.password);
      toast.success('Logged in successfully');
      navigate('/');
    } catch (err) {
      setServerError(extractErrorMessage(err));
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-md bg-white rounded-lg shadow-md p-8">
        <h1 className="text-2xl font-bold text-center mb-6">Login</h1>
        {serverError && <div className="bg-red-50 text-red-700 p-3 rounded mb-4">{serverError}</div>}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Email</label>
            <input {...register('email')} type="email" className="w-full border rounded-lg px-3 py-2" />
            {errors.email && <p className="text-red-500 text-sm mt-1">{errors.email.message}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Password</label>
            <input {...register('password')} type="password" className="w-full border rounded-lg px-3 py-2" />
            {errors.password && <p className="text-red-500 text-sm mt-1">{errors.password.message}</p>}
          </div>
          <button type="submit" disabled={isSubmitting} className="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {isSubmitting ? 'Logging in...' : 'Login'}
          </button>
        </form>
        <p className="text-center mt-4 text-sm text-gray-600">
          Don't have an account? <Link to="/register" className="text-blue-600 hover:underline">Register</Link>
        </p>
      </div>
    </div>
  );
}
